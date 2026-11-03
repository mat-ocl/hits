import html
import json
from fastapi import FastAPI, Request, Query, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from app import database
from app.config import (
    VALID_PATH_PATTERN,
    TRANSPARENT_1X1_GIF,
    TRANSPARENT_1X1_PNG,
    is_domain_allowed,
)
from app.tracker import record_visit, calculate_period_hits, calculate_time_windows
from app.version import check_for_updates
from app.icons import get_icon_path
from app.badge import build_badge_svg

app = FastAPI(title="Hit Counter Service", lifespan=database.lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["*"],
)

NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}



@app.get("/", response_class=HTMLResponse)
async def root_landing():
    ver_info = await check_for_updates()
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <title>hits - Website Hit Counter Service</title>
      <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; display: flex; justify-content: center; }}
        .container {{ max-width: 720px; width: 100%; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.25rem; border: 1px solid #334155; }}
        h1 {{ margin-top: 0; font-size: 1.6rem; }}
        h3 {{ margin-top: 0; color: #38bdf8; font-size: 1rem; }}
        p {{ color: #cbd5e1; line-height: 1.5; }}
        code {{ color: #38bdf8; background: #334155; padding: 0.2rem 0.45rem; border-radius: 4px; font-size: 0.9rem; }}
        ul {{ color: #cbd5e1; line-height: 1.8; padding-left: 1.25rem; }}
        .footer {{ text-align: center; margin-top: 2rem; color: #64748b; font-size: 0.8rem; }}
        .footer a {{ color: #94a3b8; text-decoration: none; }}
        .version-badge {{ display: inline-block; padding: 0.1rem 0.4rem; font-size: 0.75rem; background: #1e293b; border: 1px solid #334155; border-radius: 4px; color: #94a3b8; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="card">
          <h1>hits</h1>
          <p>Lightweight, self-hosted website visitor &amp; hit counter service.</p>
          <h3>Endpoints</h3>
          <ul>
            <li><code>/{{domain.tld}}/{{path}}.svg</code> &mdash; Customizable SVG hit badge</li>
            <li><code>/{{domain.tld}}/{{path}}.gif</code> &mdash; Silent 1&times;1 tracking pixel</li>
            <li><code>/{{domain.tld}}/{{path}}.json</code> &mdash; JSON hit metrics API</li>
            <li><code>/{{domain.tld}}/{{path}}</code> &mdash; Analytics dashboard</li>
          </ul>
        </div>
        <div class="footer">
          Powered by <a href="https://github.com/mat-ocl/hits" target="_blank" rel="noopener noreferrer">mat-ocl/hits</a>
          <span class="version-badge">v{html.escape(ver_info["current"])}</span>
        </div>
      </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/health")
async def health_check():
    if not database.redis_client:
        return JSONResponse(status_code=503, content={"status": "error", "detail": "Redis not initialized"})
    try:
        await database.redis_client.ping()
        return {"status": "ok"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "error", "detail": "Redis unavailable"})


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    return PlainTextResponse(content="User-agent: *\nDisallow: /\n")


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


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
    page_key = path.removesuffix(".svg").removesuffix(".gif").removesuffix(".png").removesuffix(".json").strip("/")
    if len(page_key) > 255 or not VALID_PATH_PATTERN.match(page_key):
        return Response(content="Invalid tracking path", status_code=400)
    if not is_domain_allowed(page_key):
        return Response(content="Domain not allowed", status_code=403)

    is_preview = "preview" in request.query_params or "no_count" in request.query_params
    should_link = link or ("link" in request.query_params)

    # Silent 1x1 Pixel
    if path.endswith(".gif") or path.endswith(".png"):
        if not is_preview:
            await record_visit(page_key, request, user_agent or "", x_forwarded_for, purpose, sec_purpose)
        is_png = path.endswith(".png")
        return Response(
            content=TRANSPARENT_1X1_PNG if is_png else TRANSPARENT_1X1_GIF,
            media_type="image/png" if is_png else "image/gif",
            headers=NO_CACHE_HEADERS,
        )
    # --- JSON Endpoint (.json) ---
    if path.endswith(".json"):
        if not is_preview:
            await record_visit(page_key, request, user_agent or "", x_forwarded_for, purpose, sec_purpose)

        stored_total = int(await database.redis_client.get(f"hits:{page_key}") or 0)
        daily_data = await database.redis_client.hgetall(f"hits:{page_key}:daily")
        metrics = calculate_time_windows(daily_data)
        total_hits = max(stored_total, sum(int(v) for v in daily_data.values()))

        return JSONResponse(
            content={
                "page": page_key,
                "total": total_hits,
                "today": metrics["today"],
                "last_7_days": metrics["weekly"],
                "last_30_days": metrics["monthly"],
                "daily": daily_data,
            },
            headers=NO_CACHE_HEADERS,
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
            headers=NO_CACHE_HEADERS,
        )


    # HTML Dashboard
    stored_total = int(await database.redis_client.get(f"hits:{page_key}") or 0)
    daily_data = await database.redis_client.hgetall(f"hits:{page_key}:daily")
    metrics = calculate_time_windows(daily_data)
    total_hits = max(stored_total, sum(int(v) for v in daily_data.values()))

    ver_info = await check_for_updates()
    safe_page_key = html.escape(page_key, quote=True)
    safe_current_ver = html.escape(ver_info["current"])
    safe_latest_ver = html.escape(ver_info["latest"])

    # Dynamic update badge next to current version
    update_badge_html = ""
    if ver_info["has_update"]:
        update_badge_html = f"""
        <span class="update-arrow">&rarr;</span>
        <a href="https://github.com/mat-ocl/hits/releases/latest" target="_blank" rel="noopener noreferrer" class="update-badge" title="View latest release notes">
          <span class="dot"></span>
          <span class="badge-text-idle">v{safe_latest_ver}</span>
          <span class="badge-text-hover">Update available: v{safe_latest_ver}</span>
        </a>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <title>Analytics - {safe_page_key}</title>
      <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
      <style>
        :root {{ color-scheme: dark; }}
        body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; display: flex; justify-content: center; }}
        .container {{ max-width: 850px; width: 100%; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem; }}
        .header-actions {{ display: flex; align-items: center; gap: 1rem; }}
        .gh-link {{ display: inline-flex; align-items: center; gap: 0.4rem; color: #94a3b8; text-decoration: none; font-size: 0.85rem; font-weight: 500; padding: 0.4rem 0.75rem; border-radius: 6px; border: 1px solid #334155; transition: all 0.2s ease; }}
        .gh-link:hover {{ color: #f8fafc; background: #1e293b; border-color: #475569; }}
        .gh-link svg {{ width: 16px; height: 16px; fill: currentColor; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; border: 1px solid #334155; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }}
        .stat-box {{ background: #1e293b; padding: 1.25rem; border-radius: 10px; border: 1px solid #334155; }}
        .stat-value {{ font-size: 1.75rem; font-weight: 700; color: #38bdf8; margin-top: 0.25rem; }}
        .stat-label {{ font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; font-weight: 600; letter-spacing: 0.05em; }}
        code {{ color: #38bdf8; background: #334155; padding: 0.2rem 0.4rem; border-radius: 4px; }}

        /* Badge Builder Form & Embeds */
        fieldset {{ border: 0; margin: 0; padding: 0; }}
        legend {{ font-size: 1.05rem; font-weight: 600; color: #f8fafc; margin-bottom: 1rem; padding: 0; }}
        .builder-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1.15rem; margin-bottom: 1.25rem; }}
        .form-field {{ display: flex; flex-direction: column; }}
        .form-field label {{ font-size: 0.8rem; font-weight: 600; color: #cbd5e1; margin-bottom: 0.35rem; }}
        .form-field input, .form-field select {{
          font-size: 1rem;
          padding: 0.55rem 0.75rem;
          min-height: 42px;
          border-radius: 6px;
          border: 1px solid #475569;
          background: #0f172a;
          color: #f8fafc;
          box-sizing: border-box;
        }}
        .form-field input:focus-visible, .form-field select:focus-visible, .copy-btn:focus-visible {{
          outline: 2px solid #38bdf8;
          outline-offset: 2px;
        }}
        .form-field input:user-invalid {{ border-color: #ef4444; }}
        .preview-bar {{
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 1rem;
          padding: 0.85rem 1rem;
          background: #0f172a;
          border: 1px solid #334155;
          border-radius: 8px;
          margin-bottom: 1.25rem;
          flex-wrap: wrap;
        }}
        .preview-label {{ font-size: 0.8rem; color: #94a3b8; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }}
        .snippet-list {{ display: flex; flex-direction: column; gap: 0.75rem; }}
        .snippet-row {{ display: flex; flex-direction: column; gap: 0.3rem; }}
        .snippet-title {{ font-size: 0.75rem; color: #94a3b8; font-weight: 600; }}
        .snippet-box {{
          display: flex;
          align-items: center;
          gap: 0.5rem;
          background: #0f172a;
          border: 1px solid #334155;
          border-radius: 6px;
          padding: 0.45rem 0.65rem;
        }}
        .snippet-code {{
          flex: 1;
          font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
          font-size: 0.82rem;
          color: #e2e8f0;
          background: transparent;
          padding: 0;
          overflow-x: auto;
          white-space: nowrap;
        }}
        .copy-btn {{
          background: #334155;
          color: #f8fafc;
          border: 1px solid #475569;
          border-radius: 5px;
          padding: 0.35rem 0.7rem;
          font-size: 0.78rem;
          font-weight: 600;
          cursor: pointer;
          transition: background 0.15s ease;
          flex-shrink: 0;
        }}
        .copy-btn:hover {{ background: #475569; }}

        /* Footer & Version Badges */
        .footer {{ display: flex; justify-content: center; align-items: center; margin-top: 2rem; color: #64748b; font-size: 0.8rem; flex-wrap: wrap; gap: 0.35rem; }}
        .footer a {{ color: #94a3b8; text-decoration: none; }}
        .footer a:hover {{ text-decoration: underline; }}
        .version-badge {{ display: inline-block; padding: 0.1rem 0.4rem; font-size: 0.75rem; background: #1e293b; border: 1px solid #334155; border-radius: 4px; color: #94a3b8; }}
        
        .update-arrow {{ color: #475569; font-size: 0.85rem; user-select: none; margin: 0 0.1rem; }}
        
        /* Pulsing Update Badge */
        .update-badge {{
          display: inline-flex;
          align-items: center;
          gap: 0.35rem;
          padding: 0.1rem 0.45rem;
          font-size: 0.75rem;
          font-weight: 600;
          color: #f87171;
          background: rgba(239, 68, 68, 0.12);
          border: 1px solid rgba(239, 68, 68, 0.35);
          border-radius: 4px;
          text-decoration: none !important;
          animation: pulse-border 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
          transition: all 0.2s ease-in-out;
        }}
        .update-badge:hover {{
          background: rgba(239, 68, 68, 0.22);
          border-color: #ef4444;
          color: #fca5a5;
        }}
        .badge-text-hover {{ display: none; }}
        .update-badge:hover .badge-text-idle {{ display: none; }}
        .update-badge:hover .badge-text-hover {{ display: inline; }}

        /* Pulsing Dot */
        .dot {{
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background-color: #ef4444;
          box-shadow: 0 0 6px #ef4444;
        }}

        @keyframes pulse-border {{
          0%, 100% {{ opacity: 1; }}
          50% {{ opacity: 0.45; }}
        }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h2>Analytics for <code>{safe_page_key}</code></h2>
          <div class="header-actions">
            <a href="https://github.com/mat-ocl/hits" target="_blank" rel="noopener noreferrer" class="gh-link">
              <svg viewBox="0 0 24 24"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
              GitHub
            </a>
            <img src="/{safe_page_key}.svg?preview" alt="Badge" />
          </div>
        </div>
        <div class="stats-grid">
          <div class="stat-box"><div class="stat-label">Today</div><div class="stat-value">{metrics["today"]}</div></div>
          <div class="stat-box"><div class="stat-label">Last 7 Days</div><div class="stat-value">{metrics["weekly"]}</div></div>
          <div class="stat-box"><div class="stat-label">Last 30 Days</div><div class="stat-value">{metrics["monthly"]}</div></div>
          <div class="stat-box"><div class="stat-label">All-Time</div><div class="stat-value">{total_hits}</div></div>
        </div>
        <div class="card"><canvas id="hitsChart"></canvas></div>
        <div class="card">
          <form id="badgeBuilderForm" action="/{safe_page_key}.svg" method="GET">
            <fieldset>
              <legend>Badge &amp; Embed Builder</legend>
              <div class="builder-grid">
                <div class="form-field">
                  <label for="b-style">Style</label>
                  <select id="b-style" name="style">
                    <option value="flat">flat</option>
                    <option value="flat-square">flat-square</option>
                    <option value="plastic">plastic</option>
                    <option value="for-the-badge">for-the-badge</option>
                    <option value="social">social</option>
                  </select>
                </div>
                <div class="form-field">
                  <label for="b-period">Period</label>
                  <select id="b-period" name="period">
                    <option value="all">all-time</option>
                    <option value="today">today</option>
                    <option value="7d">last 7 days (7d)</option>
                    <option value="30d">last 30 days (30d)</option>
                  </select>
                </div>
                <div class="form-field">
                  <label for="b-label">Custom Label</label>
                  <input type="text" id="b-label" name="label" placeholder="hits" maxlength="40" />
                </div>
                <div class="form-field">
                  <label for="b-color">Badge Color</label>
                  <input type="text" id="b-color" name="color" value="4c1" maxlength="20" autocorrect="off" autocapitalize="off" spellcheck="false" />
                </div>
                <div class="form-field">
                  <label for="b-label-color">Label Color</label>
                  <input type="text" id="b-label-color" name="labelColor" value="555" maxlength="20" autocorrect="off" autocapitalize="off" spellcheck="false" />
                </div>
                <div class="form-field">
                  <label for="b-logo">Logo (Simple Icons)</label>
                  <input type="text" id="b-logo" name="logo" placeholder="github, python..." maxlength="40" autocorrect="off" autocapitalize="off" spellcheck="false" />
                </div>
              </div>
              <div class="preview-bar">
                <span class="preview-label">Live Preview</span>
                <img id="builderPreviewImg" src="/{safe_page_key}.svg?preview" alt="Live badge preview" />
              </div>
              <div class="snippet-list">
                <div class="snippet-row">
                  <span class="snippet-title">Markdown Badge</span>
                  <div class="snippet-box">
                    <code id="snip-md" class="snippet-code"></code>
                    <button type="button" class="copy-btn" data-copy-target="snip-md">Copy</button>
                  </div>
                </div>
                <div class="snippet-row">
                  <span class="snippet-title">HTML Badge</span>
                  <div class="snippet-box">
                    <code id="snip-html" class="snippet-code"></code>
                    <button type="button" class="copy-btn" data-copy-target="snip-html">Copy</button>
                  </div>
                </div>
                <div class="snippet-row">
                  <span class="snippet-title">Silent Tracking Pixel (1&times;1 GIF)</span>
                  <div class="snippet-box">
                    <code id="snip-pixel" class="snippet-code"></code>
                    <button type="button" class="copy-btn" data-copy-target="snip-pixel">Copy</button>
                  </div>
                </div>
                <div class="snippet-row">
                  <span class="snippet-title">JSON Metrics Endpoint</span>
                  <div class="snippet-box">
                    <code id="snip-json" class="snippet-code"></code>
                    <button type="button" class="copy-btn" data-copy-target="snip-json">Copy</button>
                  </div>
                </div>
              </div>
            </fieldset>
          </form>
        </div>
        <div class="footer">
          Powered by <a href="https://github.com/mat-ocl/hits" target="_blank" rel="noopener noreferrer">mat-ocl/hits</a>
          <span class="version-badge">v{safe_current_ver}</span>
          {update_badge_html}
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

        const pageKey = {json.dumps(page_key)};
        const builderForm = document.getElementById('badgeBuilderForm');
        const previewImg = document.getElementById('builderPreviewImg');
        const snipMd = document.getElementById('snip-md');
        const snipHtml = document.getElementById('snip-html');
        const snipPixel = document.getElementById('snip-pixel');
        const snipJson = document.getElementById('snip-json');

        function updateEmbeds() {{
          const params = new URLSearchParams();
          const style = document.getElementById('b-style').value;
          const period = document.getElementById('b-period').value;
          const label = document.getElementById('b-label').value.trim();
          const color = document.getElementById('b-color').value.trim();
          const labelColor = document.getElementById('b-label-color').value.trim();
          const logo = document.getElementById('b-logo').value.trim();

          if (style && style !== 'flat') params.set('style', style);
          if (period && period !== 'all') params.set('period', period);
          if (label) params.set('label', label);
          if (color && color !== '4c1') params.set('color', color);
          if (labelColor && labelColor !== '555') params.set('labelColor', labelColor);
          if (logo) params.set('logo', logo);

          const qs = params.toString();
          const querySuffix = qs ? `?${{qs}}` : '';
          const previewParams = new URLSearchParams(params);
          previewParams.set('preview', '');
          previewImg.src = `/${{pageKey}}.svg?${{previewParams.toString()}}`;

          const origin = window.location.origin;
          const badgeUrl = `${{origin}}/${{pageKey}}.svg${{querySuffix}}`;
          const dashUrl = `${{origin}}/${{pageKey}}`;
          snipMd.textContent = `[![Hits](${{badgeUrl}})](${{dashUrl}})`;
          snipHtml.textContent = `<a href="${{dashUrl}}"><img src="${{badgeUrl}}" alt="Hits"></a>`;
          snipPixel.textContent = `<img src="${{origin}}/${{pageKey}}.gif" alt="" width="1" height="1" style="display:none">`;
          snipJson.textContent = `${{origin}}/${{pageKey}}.json`;
        }}

        builderForm.addEventListener('submit', (e) => e.preventDefault());
        builderForm.addEventListener('input', updateEmbeds);
        builderForm.addEventListener('change', updateEmbeds);

        document.querySelectorAll('.copy-btn').forEach((btn) => {{
          btn.addEventListener('click', async () => {{
            const targetId = btn.getAttribute('data-copy-target');
            const targetEl = document.getElementById(targetId);
            if (!targetEl) return;
            try {{
              await navigator.clipboard.writeText(targetEl.textContent);
              const prev = btn.textContent;
              btn.textContent = 'Copied!';
              setTimeout(() => {{ btn.textContent = prev; }}, 1500);
            }} catch {{
              btn.textContent = 'Error';
            }}
          }});
        }});

        updateEmbeds();
      </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)