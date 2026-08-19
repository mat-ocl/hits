from contextlib import asynccontextmanager
import redis.asyncio as redis
from app.config import REDIS_URL

redis_client: redis.Redis | None = None
http_client = None

@asynccontextmanager
async def lifespan(app):
    global redis_client, http_client
    import httpx
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    http_client = httpx.AsyncClient(timeout=3.0)
    yield
    await redis_client.close()
    await http_client.aclose()