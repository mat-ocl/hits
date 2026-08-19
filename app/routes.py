from fastapi import FastAPI, Request, Query, Header, Response
from fastapi.responses import HTMLResponse
from app import database
from app.config import VALID_PATH_PATTERN, TRANSPARENT_1X1_GIF
from app.tracker import record_visit, calculate_period_hits, calculate_time_windows
from app.icons import get_icon_path
from app.badge import build_badge_svg

app = FastAPI(title="Hit Counter Service", lifespan=database.lifespan)

@app.get("/{path:path}")
async def route_handler(
    path: str,
    request: Request,
    period: str = Query(default="all"),
    style: str = Query(default="flat"),
    label: str | None = Query(default=None),
    color: str = Query(default="4c1"),
    label_color: str = Query(default="555", alias="labelColor"),
    logo_color: str = Query(default="fff", alias="logoColor"),
    logo: str | None = Query(default=None),
    link: bool = Query(default=False),
    user_agent: str | None = Header(default=""),
    x_forwarded_for: str | None = Header(default=None),
    purpose: str | None = Header(default=None),
    sec_purpose: str | None = Header(default=None),
):
    page_key = path.removesuffix(".svg").removesuffix(".gif").removesuffix(".png").strip("/")
    if not VALID_PATH_PATTERN.match(page_key):
        return Response(content="Invalid tracking path", status_code=400)

    is_preview = "preview" in request.query_params or "no_count" in request.query_params
    should_link = link or ("link" in request.query_params)

    # Silent 1x1 Pixel
    if path.endswith(".gif") or path.endswith(".png"):
        if not is_preview:
            await record_visit(page_key, request, user_agent or "", x_forwarded_for, purpose, sec_purpose)
        return Response(
            content=TRANSPARENT_1X1_GIF,
            media_type="image/gif",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate, max-age=0"},
        )

    # Visible SVG Badge
    if path.endswith(".svg"):
        if not is_preview:
            await record_visit(page_key, request, user_agent or "", x_forwarded_for, purpose, sec_purpose)
        default_label, display_count = await calculate_period_hits(page_key, period)
        icon_path_d = await get_icon_path(logo) if logo else None

        link_url = f"/{page_key}" if should_link else None

        return Response(
            content=build_badge_svg(
                label=label or default_label,
                count=display_count,
                color=color,
                label_color=label_color,
                style=style,
                icon_path_d=icon_path_d,
                logo_color=logo_color,
                link_url=link_url,
            ),
            media_type="image/svg+xml",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate, max-age=0"},
        )

    # HTML Dashboard
    stored_total = int(await database.redis_client.get(f"hits:{page_key}") or 0)
    daily_data = await database.redis_client.hgetall(f"hits:{page_key}:daily")
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
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem; }}
        .header-actions {{ display: flex; align-items: center; gap: 1rem; }}
        .gh-link {{ display: inline-flex; align-items: center; gap: 0.4rem; color: #94a3b8; text-decoration: none; font-size: 0.85rem; font-weight: 500; padding: 0.4rem 0.75rem; border-radius: 6px; border: 1px solid #334155; transition: all 0.2s ease; }}
        .gh-link:hover {{ color: #f8fafc; background: #1e293b; border-color: #475569; }}
        .gh-link svg {{ width: 16px; height: 16px; fill: currentColor; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1.5rem; }}
        .stat-box {{ background: #1e293b; padding: 1.25rem; border-radius: 10px; border: 1px solid #334155; }}
        .stat-value {{ font-size: 1.75rem; font-weight: 700; color: #38bdf8; margin-top: 0.25rem; }}
        .stat-label {{ font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; font-weight: 600; letter-spacing: 0.05em; }}
        code {{ color: #38bdf8; background: #334155; padding: 0.2rem 0.4rem; border-radius: 4px; }}
        .footer {{ text-align: center; margin-top: 2rem; color: #64748b; font-size: 0.8rem; }}
        .footer a {{ color: #94a3b8; text-decoration: none; }}
        .footer a:hover {{ text-decoration: underline; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h2>Analytics for <code>{page_key}</code></h2>
          <div class="header-actions">
            <a href="https://github.com/mat-ocl/hits" target="_blank" rel="noopener noreferrer" class="gh-link">
              <svg viewBox="0 0 24 24">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
              </svg>
              GitHub
            </a>
            <img src="/{page_key}.svg?preview" alt="Badge" />
          </div>
        </div>
        <div class="stats-grid">
          <div class="stat-box"><div class="stat-label">Today</div><div class="stat-value">{metrics["today"]}</div></div>
          <div class="stat-box"><div class="stat-label">Last 7 Days</div><div class="stat-value">{metrics["weekly"]}</div></div>
          <div class="stat-box"><div class="stat-label">Last 30 Days</div><div class="stat-value">{metrics["monthly"]}</div></div>
          <div class="stat-box"><div class="stat-label">All-Time</div><div class="stat-value">{total_hits}</div></div>
        </div>
        <div class="card"><canvas id="hitsChart"></canvas></div>
        <div class="footer">
          Powered by <a href="https://github.com/mat-ocl/hits" target="_blank" rel="noopener noreferrer">mat-ocl/hits</a>
        </div>
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