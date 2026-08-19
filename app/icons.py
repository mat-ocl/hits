import re
from app import database

MEMORY_ICON_CACHE: dict[str, str] = {}
PATH_REGEX = re.compile(r'<path[^>]*d="([^"]+)"', re.IGNORECASE)

async def get_icon_path(logo_name: str) -> str | None:
    slug = logo_name.lower().strip().replace(" ", "").replace("-", "").replace(".", "dot")

    if slug in MEMORY_ICON_CACHE:
        return MEMORY_ICON_CACHE[slug]

    redis_key = f"icon:{slug}"
    if database.redis_client:
        cached_d = await database.redis_client.get(redis_key)
        if cached_d:
            MEMORY_ICON_CACHE[slug] = cached_d
            return cached_d

    url = f"https://cdn.jsdelivr.net/npm/simple-icons@v11/icons/{slug}.svg"
    try:
        if database.http_client:
            resp = await database.http_client.get(url)
            if resp.status_code == 200:
                match = PATH_REGEX.search(resp.text)
                if match:
                    path_d = match.group(1)
                    MEMORY_ICON_CACHE[slug] = path_d
                    if database.redis_client:
                        await database.redis_client.set(redis_key, path_d, ex=2592000)
                    return path_d
    except Exception:
        pass

    return None