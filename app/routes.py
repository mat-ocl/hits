import html
import json
import logging
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
from app.tracker import record_visit, calculate_period_hits, get_page_stats
from app.version import check_for_updates
from app.icons import get_icon_path
from app.badge import build_badge_svg
from app.pages import render_dashboard, render_landing

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
    return HTMLResponse(content=render_landing(ver_info))


@app.api_route("/health", methods=["GET", "HEAD"])
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


@app.api_route("/{path:path}", methods=["GET", "HEAD"])
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
    # Domains are case-insensitive, so Example.com and example.com must share one counter.
    page_key = path.removesuffix(".svg").removesuffix(".gif").removesuffix(".png").removesuffix(".json").strip("/").lower()
    if len(page_key) > 255 or not VALID_PATH_PATTERN.match(page_key):
        return Response(content="Invalid tracking path", status_code=400)
    if not is_domain_allowed(page_key):
        return Response(content="Domain not allowed", status_code=403)

    # HEAD (uptime monitors, link checkers) must not count as a visit.
    is_preview = "preview" in request.query_params or "no_count" in request.query_params or request.method == "HEAD"
    should_link = link or ("link" in request.query_params)

    if not is_preview and path.endswith((".gif", ".png", ".json", ".svg")):
        try:
            await record_visit(page_key, request, user_agent or "", x_forwarded_for, purpose, sec_purpose)
        except Exception:
            # Counting is best effort: a Redis hiccup must not break the image on someone else's site.
            logging.getLogger("uvicorn.error").exception("visit not counted")

    # Silent 1x1 Pixel
    if path.endswith(".gif") or path.endswith(".png"):
        is_png = path.endswith(".png")
        return Response(
            content=TRANSPARENT_1X1_PNG if is_png else TRANSPARENT_1X1_GIF,
            media_type="image/png" if is_png else "image/gif",
            headers=NO_CACHE_HEADERS,
        )
    # --- JSON Endpoint (.json) ---
    if path.endswith(".json"):
        stats = await get_page_stats(page_key)
        return JSONResponse(
            content={
                "page": page_key,
                "total": stats["total"],
                "today": stats["today"],
                "last_7_days": stats["weekly"],
                "last_30_days": stats["monthly"],
                "daily": stats["daily"],
            },
            headers=NO_CACHE_HEADERS,
        )
    
    # Visible SVG Badge
    if path.endswith(".svg"):
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
    stats = await get_page_stats(page_key)
    ver_info = await check_for_updates()
    return HTMLResponse(content=render_dashboard(page_key, stats, ver_info))
