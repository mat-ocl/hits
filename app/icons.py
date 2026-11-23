import re
from app import database

MAX_MEMORY_CACHE_SIZE = 512
NEGATIVE_CACHE_SENTINEL = "__NONE__"
MEMORY_ICON_CACHE: dict[str, str] = {}
PATH_REGEX = re.compile(r'<path[^>]*d="([^"]+)"', re.IGNORECASE)
SLUG_CLEAN_REGEX = re.compile(r"[^a-z0-9]")


def _cache_in_memory(slug: str, value: str) -> None:
    if len(MEMORY_ICON_CACHE) >= MAX_MEMORY_CACHE_SIZE and slug not in MEMORY_ICON_CACHE:
        oldest_key = next(iter(MEMORY_ICON_CACHE))
        MEMORY_ICON_CACHE.pop(oldest_key, None)
    MEMORY_ICON_CACHE[slug] = value


async def get_icon_path(logo_name: str) -> str | None:
    raw_slug = logo_name.lower().strip().replace(" ", "").replace("-", "").replace(".", "dot")
    slug = SLUG_CLEAN_REGEX.sub("", raw_slug)[:64]
    if not slug:
        return None

    if slug in MEMORY_ICON_CACHE:
        cached = MEMORY_ICON_CACHE[slug]
        return None if cached == NEGATIVE_CACHE_SENTINEL else cached

    redis_key = f"icon:{slug}"
    try:
        cached_d = await database.redis_client.get(redis_key)
        if cached_d:
            if cached_d == NEGATIVE_CACHE_SENTINEL:
                return None
            _cache_in_memory(slug, cached_d)
            return cached_d

        url = f"https://cdn.jsdelivr.net/npm/simple-icons@v16/icons/{slug}.svg"
        resp = await database.http_client.get(url)
        if resp.status_code == 200:
            match = PATH_REGEX.search(resp.text)
            if match:
                path_d = match.group(1)
                _cache_in_memory(slug, path_d)
                await database.redis_client.set(redis_key, path_d, ex=2592000)
                return path_d
        # Unknown icon: remember for an hour. Any other failure: only 60s, so an outage heals fast.
        if resp.status_code == 404:
            _cache_in_memory(slug, NEGATIVE_CACHE_SENTINEL)
        ttl = 3600 if resp.status_code == 404 else 60
        await database.redis_client.set(redis_key, NEGATIVE_CACHE_SENTINEL, ex=ttl)
    except Exception:
        pass
    return None
