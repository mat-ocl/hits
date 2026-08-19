import hashlib
from datetime import datetime, timezone, timedelta
from fastapi import Request
from crawlerdetect import CrawlerDetect
from app import database
from app.config import DEDUPE_WINDOW_SECONDS

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
        x_forwarded_for.split(",")[0].strip()
        if x_forwarded_for
        else (request.client.host if request.client else "unknown")
    )

    visitor_hash = hashlib.sha256(f"{client_ip}:{page_key}".encode()).hexdigest()
    dedupe_key = f"seen:{visitor_hash}"
    counter_key = f"hits:{page_key}"
    daily_key = f"hits:{page_key}:daily"

    if not (is_bot or is_prefetch) and database.redis_client:
        was_set = await database.redis_client.set(
            dedupe_key, "1", ex=DEDUPE_WINDOW_SECONDS, nx=True
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

async def calculate_period_hits(page_key: str, period: str) -> tuple[str, int]:
    if not database.redis_client:
        return "hits", 0

    if period == "all":
        count = int(await database.redis_client.get(f"hits:{page_key}") or 0)
        return "hits", count

    daily_data = await database.redis_client.hgetall(f"hits:{page_key}:daily")
    metrics = calculate_time_windows(daily_data)

    if period == "today":
        return "today", metrics["today"]
    if period in ("7d", "weekly"):
        return "7d", metrics["weekly"]
    if period in ("30d", "monthly"):
        return "30d", metrics["monthly"]

    count = int(await database.redis_client.get(f"hits:{page_key}") or 0)
    return "hits", count