import hashlib
from datetime import datetime, timezone, timedelta
from fastapi import Request
from crawlerdetect import CrawlerDetect
from app import database
from app.config import DEDUPE_WINDOW_SECONDS, HASH_SALT, TRUST_PROXY_HEADERS

crawler_detect = CrawlerDetect()

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
        x_forwarded_for.split(",")[-1].strip()
        if (TRUST_PROXY_HEADERS and x_forwarded_for)
        else (request.client.host if request.client else "unknown")
    )

    visitor_hash = hashlib.sha256(
        f"{HASH_SALT}:{today_str}:{client_ip}:{page_key}".encode()
    ).hexdigest()
    dedupe_key = f"seen:{visitor_hash}"
    counter_key = f"hits:{page_key}"
    daily_key = f"hits:{page_key}:daily"

    if not (is_bot or is_prefetch) and database.redis_client:
        was_set = (
            await database.redis_client.set(
                dedupe_key, "1", ex=DEDUPE_WINDOW_SECONDS, nx=True
            )
            if DEDUPE_WINDOW_SECONDS > 0
            else True
        )
        if was_set:
            async with database.redis_client.pipeline(transaction=True) as pipe:
                pipe.incr(counter_key)
                pipe.hincrby(daily_key, today_str, 1)
                await pipe.execute()


def calculate_time_windows(daily_data: dict[str, str]) -> dict:
    today = datetime.now(timezone.utc).date()
    today_str = today.strftime("%Y-%m-%d")

    past_7 = {(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}
    past_30 = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(29, -1, -1)]

    weekly = sum(int(v) for k, v in daily_data.items() if k in past_7)
    monthly = sum(int(v) for k, v in daily_data.items() if k in past_30)

    chart_labels = past_30
    chart_values = [int(daily_data.get(d, 0)) for d in past_30]

    return {
        "today": int(daily_data.get(today_str, 0)),
        "weekly": weekly,
        "monthly": monthly,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
    }


async def get_page_stats(page_key: str) -> dict:
    stored_total = int(await database.redis_client.get(f"hits:{page_key}") or 0)
    daily_data = await database.redis_client.hgetall(f"hits:{page_key}:daily")
    metrics = calculate_time_windows(daily_data)
    total_hits = max(stored_total, sum(int(v) for v in daily_data.values()))
    return {"total": total_hits, "daily": daily_data, **metrics}


async def calculate_period_hits(page_key: str, period: str) -> tuple[str, int]:
    if not database.redis_client:
        return "hits", 0

    today = datetime.now(timezone.utc).date()
    daily_key = f"hits:{page_key}:daily"

    if period == "today":
        val = await database.redis_client.hget(daily_key, today.strftime("%Y-%m-%d"))
        return "today", int(val or 0)

    if period in ("7d", "weekly"):
        keys = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        vals = await database.redis_client.hmget(daily_key, keys)
        return "7d", sum(int(v or 0) for v in vals)

    if period in ("30d", "monthly"):
        keys = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]
        vals = await database.redis_client.hmget(daily_key, keys)
        return "30d", sum(int(v or 0) for v in vals)

    stats = await get_page_stats(page_key)
    return "hits", stats["total"]