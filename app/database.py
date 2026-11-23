from contextlib import asynccontextmanager
import httpx
import redis.asyncio as redis
from app.config import REDIS_URL

redis_client: redis.Redis | None = None
http_client: httpx.AsyncClient | None = None

@asynccontextmanager
async def lifespan(app):
    global redis_client, http_client
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    http_client = httpx.AsyncClient(timeout=3.0)
    yield
    await redis_client.aclose()
    await http_client.aclose()
