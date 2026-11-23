import asyncio
from app import database
from app.config import (
    CURRENT_VERSION,
    GITHUB_REPO,
    VERSION_CHECK_CACHE_SECONDS,
    VERSION_CHECK_FAILURE_CACHE_SECONDS,
)

_VERSION_LOCK = asyncio.Lock()


def _ver_key(v: str) -> tuple[tuple[int, ...], int]:
    base, _, suffix = v.lstrip("v").strip().partition("-")
    nums = tuple(int(x) for x in base.split(".") if x.isdigit())
    return (nums, 0 if suffix else 1)


async def check_for_updates() -> dict:
    cache_key = "system:latest_version"
    clean_current = CURRENT_VERSION.lstrip("v").strip()

    latest_ver_str = await database.redis_client.get(cache_key)

    if not latest_ver_str and database.http_client:
        async with _VERSION_LOCK:
            latest_ver_str = await database.redis_client.get(cache_key)
            if not latest_ver_str:
                ttl = VERSION_CHECK_FAILURE_CACHE_SECONDS
                try:
                    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
                    headers = {
                        "User-Agent": "Hits-App-Version-Checker",
                        "Accept": "application/vnd.github+json",
                    }
                    # Short timeout: a slow GitHub must not hold up the page for everyone waiting on the lock.
                    resp = await database.http_client.get(url, headers=headers, timeout=1.0)
                    if resp.status_code == 200:
                        tag = resp.json().get("tag_name", "").lstrip("v").strip()
                        if tag:
                            latest_ver_str, ttl = tag, VERSION_CHECK_CACHE_SECONDS
                except Exception:
                    pass
                # On failure remember the current version for an hour so GitHub is not asked again.
                await database.redis_client.set(cache_key, latest_ver_str or clean_current, ex=ttl)

    has_update = bool(latest_ver_str and _ver_key(latest_ver_str) > _ver_key(clean_current))

    return {
        "current": clean_current,
        "latest": latest_ver_str or clean_current,
        "has_update": has_update,
    }
