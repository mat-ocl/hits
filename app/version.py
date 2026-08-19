from packaging import version
from app import database
from app.config import CURRENT_VERSION, GITHUB_REPO, VERSION_CHECK_CACHE_SECONDS

async def check_for_updates() -> dict:
    cache_key = "system:latest_version"
    
    latest_ver_str = None
    if database.redis_client:
        latest_ver_str = await database.redis_client.get(cache_key)

    if not latest_ver_str and database.http_client:
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            headers = {
                "User-Agent": "Hits-App-Version-Checker",
                "Accept": "application/vnd.github+json",
            }
            resp = await database.http_client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                tag = data.get("tag_name", "").lstrip("v").strip()
                if tag:
                    latest_ver_str = tag
                    if database.redis_client:
                        await database.redis_client.set(
                            cache_key, 
                            latest_ver_str, 
                            ex=VERSION_CHECK_CACHE_SECONDS
                        )
        except Exception:
            pass

    has_update = False
    clean_current = CURRENT_VERSION.lstrip("v").strip()

    if latest_ver_str:
        try:
            has_update = version.parse(latest_ver_str) > version.parse(clean_current)
        except Exception:
            has_update = latest_ver_str != clean_current

    return {
        "current": clean_current,
        "latest": latest_ver_str or clean_current,
        "has_update": has_update,
    }