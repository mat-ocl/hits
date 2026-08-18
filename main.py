import hashlib
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from crawlerdetect import CrawlerDetect
from fastapi import FastAPI, Header, Query, Request, Response
from fastapi.responses import HTMLResponse
import redis.asyncio as redis

crawler_detect = CrawlerDetect()
redis_client: redis.Redis | None = None

# Minimal 43-byte base64/hex 1x1 transparent GIF
TRANSPARENT_1X1_GIF = bytes.fromhex(
    "47494638396101000100800000ffffff00000021f90401000000002c00000000010001000002024401003b"
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_client = redis.from_url(redis_url, decode_responses=True)
    yield
    await redis_client.aclose()

app = FastAPI(lifespan=lifespan)

# --- Shared Tracking Logic ---
async def record_visit(
    page_key: str,
    request: Request,
    user_agent: str,
    x_forwarded_for: str | None,
    purpose: str | None,
    sec_purpose: str | None,
):
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    is_prefetch = purpose == "prefetch" or sec_purpose in ("prefetch", "prerender")
    is_bot = crawler_detect.isCrawler(user_agent) if user_agent else False

    client_ip = (
        x_forwarded_for.split(",")[0].strip()
        if x_forwarded_for
        else (request.client.host if request.client else "unknown")
    )

    visitor_hash = hashlib.sha256(f"{client_ip}:{page_key}".encode()).hexdigest()
    dedupe_key = f"seen:{visitor_hash}"
    counter_key = f"hits:{page_key}"
    daily_key = f"hits:{page_key}:daily"

    if not (is_bot or is_prefetch):
        was_set = await redis_client.set(dedupe_key, "1", ex=600, nx=True)
        if was_set:
            async with redis_client.pipeline(transaction=True) as pipe:
                pipe.incr(counter_key)
                pipe.hincrby(daily_key, today_str, 1)
                await pipe.execute()

# Helper: Approximate text width in pixels for clean SVG rendering
def estimate_text_width(text: str) -> int:
    return int(len(text) * 7.5 + 14)

def build_badge_svg(label: str, count: int, color: str = "4c1") -> str:
    count_str = str(count)
    label_width = estimate_text_width(label)
    count_width = estimate_text_width(count_str)
    total_width = label_width + count_width

    label_x = label_width / 2
    count_x = label_width + (count_width / 2)

    # Normalize hex color if '#' is omitted
    bg_color = color if color.startswith("#") else f"#{color}"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20">
  <linearGradient id="b" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <mask id="a">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </mask>
  <g mask="url(#a)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{count_width}" height="20" fill="{bg_color}"/>
    <rect width="{total_width}" height="20" fill="url(#b)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="{label_x}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{label_x}" y="14">{label}</text>
    <text x="{count_x}" y="15" fill="#010101" fill-opacity=".3">{count_str}</text>
    <text x="{count_x}" y="14">{count_str}</text>
  </g>
</svg>"""

async def calculate_period_hits(page_key: str, period: str) -> tuple[str, int]:
    normalized_period = period.lower()

    if normalized_period in ("today", "1d"):
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        hits = int(await redis_client.hget(f"hits:{page_key}:daily", today_str) or 0)
        return "today", hits

    if normalized_period in ("7d", "week", "weekly"):
        today = datetime.now(timezone.utc).date()
        past_7_days = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        values = await redis_client.hmget(f"hits:{page_key}:daily", past_7_days)
        hits = sum(int(v) for v in values if v is not None)
        return "7d hits", hits

    if normalized_period in ("30d", "month", "monthly"):
        today = datetime.now(timezone.utc).date()
        past_30_days = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]
        values = await redis_client.hmget(f"hits:{page_key}:daily", past_30_days)
        hits = sum(int(v) for v in values if v is not None)
        return "30d hits", hits

    # Default to all-time hits
    hits = int(await redis_client.get(f"hits:{page_key}") or 0)
    return "hits", hits

def calculate_time_windows(daily_data: dict[str, str]):
    today = datetime.now(timezone.utc).date()
    
    # Generate past 30 day labels with zero-filled defaults
    past_30_days = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(29, -1, -1)]
    chart_labels = past_30_days
    chart_values = [int(daily_data.get(d, 0)) for d in past_30_days]

    weekly_total = sum(chart_values[-7:])   # Last 7 days
    monthly_total = sum(chart_values)       # Last 30 days
    today_total = chart_values[-1]          # Today

    return {
        "today": today_total,
        "weekly": weekly_total,
        "monthly": monthly_total,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
    }

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

# 1. JSON Statistics Endpoint
@app.get("/{path:path}/stats.json")
async def get_stats_json(path: str):
    page_key = path.strip("/")
    stored_total = int(await redis_client.get(f"hits:{page_key}") or 0)
    daily_hits = await redis_client.hgetall(f"hits:{page_key}:daily")
    metrics = calculate_time_windows(daily_hits)

    return {
        "path": page_key,
        "total": max(stored_total, sum(int(v) for v in daily_hits.values())),
        "today": metrics["today"],
        "past_7_days": metrics["weekly"],
        "past_30_days": metrics["monthly"],
        "daily_history": dict(sorted(daily_hits.items())),
    }

# 2. Silent JS Beacon Endpoint (Returns 204 No Content)
@app.get("/{path:path}/track")
@app.post("/{path:path}/track")
async def track_beacon(
    path: str,
    request: Request,
    user_agent: str | None = Header(default=""),
    x_forwarded_for: str | None = Header(default=None),
    purpose: str | None = Header(default=None),
    sec_purpose: str | None = Header(default=None),
):
    page_key = path.strip("/")
    await record_visit(page_key, request, user_agent or "", x_forwarded_for, purpose, sec_purpose)
    return Response(status_code=204)


# 3. Badge, Pixel, and Dashboard Router
@app.get("/{path:path}")
async def route_handler(
    path: str,
    request: Request,
    period: str = Query(default="all"),
    label: str | None = Query(default=None),
    color: str = Query(default="4c1"),
    user_agent: str | None = Header(default=""),
    x_forwarded_for: str | None = Header(default=None),
    purpose: str | None = Header(default=None),
    sec_purpose: str | None = Header(default=None),
):
    # --- Silent 1x1 Pixel Route (.gif, .png) ---
    if path.endswith(".gif") or path.endswith(".png"):
        page_key = path.removesuffix(".gif").removesuffix(".png").strip("/")
        await record_visit(page_key, request, user_agent or "", x_forwarded_for, purpose, sec_purpose)
        return Response(
            content=TRANSPARENT_1X1_GIF,
            media_type="image/gif",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    # --- Visible SVG Badge Route (.svg) ---
    if path.endswith(".svg"):
        page_key = path.removesuffix(".svg").strip("/")
        await record_visit(page_key, request, user_agent or "", x_forwarded_for, purpose, sec_purpose)
        default_label, display_count = await calculate_period_hits(page_key, period)
        return Response(
            content=build_badge_svg(label or default_label, display_count, color),
            media_type="image/svg+xml",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    # --- HTML Dashboard (No Extension) ---
    page_key = path.strip("/")
    if not page_key:
        return HTMLResponse("<h1>Hit Counter Service</h1><p>Append <code>.svg</code> for badges or <code>.gif</code> for silent tracking.</p>")

    stored_total = int(await redis_client.get(f"hits:{page_key}") or 0)
    daily_data = await redis_client.hgetall(f"hits:{page_key}:daily")
    metrics = calculate_time_windows(daily_data)
    total_hits = max(stored_total, sum(int(v) for v in daily_data.values()))

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <title>Analytics - {page_key}</title>
      <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
      <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; display: flex; justify-content: center; }}
        .container {{ max-width: 850px; width: 100%; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1.5rem; }}
        .stat-box {{ background: #1e293b; padding: 1.25rem; border-radius: 10px; border: 1px solid #334155; }}
        .stat-value {{ font-size: 1.75rem; font-weight: 700; color: #38bdf8; margin-top: 0.25rem; }}
        .stat-label {{ font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; font-weight: 600; letter-spacing: 0.05em; }}
        code {{ color: #38bdf8; background: #334155; padding: 0.2rem 0.4rem; border-radius: 4px; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h2>Analytics for <code>{page_key}</code></h2>
          <img src="/{page_key}.svg" alt="Badge" />
        </div>
        <div class="stats-grid">
          <div class="stat-box"><div class="stat-label">Today</div><div class="stat-value">{metrics["today"]}</div></div>
          <div class="stat-box"><div class="stat-label">Last 7 Days</div><div class="stat-value">{metrics["weekly"]}</div></div>
          <div class="stat-box"><div class="stat-label">Last 30 Days</div><div class="stat-value">{metrics["monthly"]}</div></div>
          <div class="stat-box"><div class="stat-label">All-Time</div><div class="stat-value">{total_hits}</div></div>
        </div>
        <div class="card"><canvas id="hitsChart"></canvas></div>
      </div>
      <script>
        const ctx = document.getElementById('hitsChart').getContext('2d');
        new Chart(ctx, {{
          type: 'line',
          data: {{
            labels: {metrics["chart_labels"]},
            datasets: [{{
              label: 'Daily Hits (Past 30 Days)',
              data: {metrics["chart_values"]},
              borderColor: '#38bdf8',
              backgroundColor: 'rgba(56, 189, 248, 0.15)',
              borderWidth: 2,
              pointRadius: 3,
              fill: true,
              tension: 0.25
            }}]
          }},
          options: {{
            responsive: true,
            scales: {{
              x: {{ grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }},
              y: {{ grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8', precision: 0 }}, beginAtZero: true }}
            }},
            plugins: {{ legend: {{ labels: {{ color: '#f8fafc' }} }} }}
          }}
        }});
      </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)