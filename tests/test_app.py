from __future__ import annotations
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import badge, config, database, icons, tracker, version
from app.routes import (
    favicon,
    health_check,
    robots_txt,
    root_landing,
    route_handler,
)


class FakePipeline:
    def __init__(self, store: FakeRedis):
        self.store = store
        self.ops = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def incr(self, key: str):
        self.ops.append(("incr", key))

    def hincrby(self, key: str, field: str, amount: int):
        self.ops.append(("hincrby", key, field, amount))

    async def execute(self):
        for op in self.ops:
            if op[0] == "incr":
                _, key = op
                self.store.kv[key] = str(int(self.store.kv.get(key, "0")) + 1)
            elif op[0] == "hincrby":
                _, key, field, amount = op
                h = self.store.hashes.setdefault(key, {})
                h[field] = str(int(h.get(field, "0")) + amount)
        self.ops.clear()


class FakeRedis:
    def __init__(self):
        self.kv: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}

    async def ping(self):
        return True

    async def get(self, key: str) -> str | None:
        return self.kv.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self.kv:
            return False
        self.kv[key] = value
        return True

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    async def hget(self, key: str, field: str) -> str | None:
        return self.hashes.get(key, {}).get(field)

    async def hmget(self, key: str, fields: list[str]) -> list[str | None]:
        h = self.hashes.get(key, {})
        return [h.get(f) for f in fields]

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self)


class DummyHttpResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class DummyHttpClient:
    def __init__(self, response: DummyHttpResponse):
        self.response = response

    async def get(self, url: str, headers: dict | None = None) -> DummyHttpResponse:
        return self.response


class DummyClient:
    def __init__(self, host: str = "203.0.113.10"):
        self.host = host


class DummyRequest:
    def __init__(self, query_params: dict[str, str] | None = None, host: str = "203.0.113.10"):
        self.query_params = query_params or {}
        self.client = DummyClient(host)


class TestHitsApp(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake_redis = FakeRedis()
        database.redis_client = self.fake_redis
        database.http_client = None
        icons.MEMORY_ICON_CACHE.clear()
        config.ALLOWED_DOMAINS = ["*"]

    def test_badge_styles_and_dimensions(self):
        styles = ["flat", "flat-square", "plastic", "for-the-badge", "social"]
        rendered = {s: badge.build_badge_svg("hits", 123, style=s) for s in styles}
        self.assertEqual(len(set(rendered.values())), 5)
        self.assertIn('height="28"', rendered["for-the-badge"])
        self.assertIn("HITS", rendered["for-the-badge"])
        self.assertIn('linearGradient id="p"', rendered["plastic"])
        self.assertIn('stroke="#d5d5d5"', rendered["social"])
        self.assertNotIn("<mask", rendered["flat-square"])

    def test_badge_xss_sanitization(self):
        svg = badge.build_badge_svg(
            label='<script>alert("xss")</script>',
            count=7,
            color='" onload="alert(1)',
            label_color="javascript:alert(1)",
            link_url='https://example.com/?a="><script>',
        )
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)
        self.assertNotIn('onload="alert(1)"', svg)
        self.assertIn('fill="#4c1"', svg)
        self.assertIn('fill="#555"', svg)

    def test_domain_allowlist(self):
        config.ALLOWED_DOMAINS = ["example.com", "*.blog.org"]
        self.assertTrue(config.is_domain_allowed("example.com/page"))
        self.assertFalse(config.is_domain_allowed("evil.com/page"))
        self.assertTrue(config.is_domain_allowed("blog.org/post"))
        self.assertTrue(config.is_domain_allowed("dev.blog.org/post"))
        self.assertFalse(config.is_domain_allowed("myblog.org/post"))

    async def test_icon_slug_sanitization_and_negative_cache(self):
        self.assertIsNone(await icons.get_icon_path("../../../etc"))
        icons._cache_in_memory("unknownicon", icons.NEGATIVE_CACHE_SENTINEL)
        self.assertIsNone(await icons.get_icon_path("unknown-icon"))

    async def test_system_routes(self):
        root_resp = await root_landing()
        self.assertEqual(root_resp.status_code, 200)
        self.assertIn(b"hits", root_resp.body)

        health_resp = await health_check()
        self.assertEqual(health_resp, {"status": "ok"})

        robots_resp = await robots_txt()
        self.assertEqual(robots_resp.status_code, 200)
        self.assertIn(b"Disallow: /", robots_resp.body)

        fav_resp = await favicon()
        self.assertEqual(fav_resp.status_code, 204)

    async def test_tracking_deduplication_and_filters(self):
        req = DummyRequest()
        # 1. First visit increments counter
        resp1 = await route_handler(
            path="example.com/home.svg",
            request=req,
            period="all",
            style="flat",
            label=None,
            color="4c1",
            label_color="555",
            logo_color="fff",
            logo=None,
            link=False,
            user_agent="Mozilla/5.0",
            x_forwarded_for="198.51.100.7",
            purpose=None,
            sec_purpose=None,
        )
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(self.fake_redis.kv.get("hits:example.com/home"), "1")

        # 2. Duplicate visit from same IP is deduplicated
        await route_handler(
            path="example.com/home.svg",
            request=req,
            period="all",
            style="flat",
            label=None,
            color="4c1",
            label_color="555",
            logo_color="fff",
            logo=None,
            link=False,
            user_agent="Mozilla/5.0",
            x_forwarded_for="198.51.100.7",
            purpose=None,
            sec_purpose=None,
        )
        self.assertEqual(self.fake_redis.kv.get("hits:example.com/home"), "1")

        # 3. Bot User-Agent is ignored even from a new IP
        await route_handler(
            path="example.com/home.svg",
            request=req,
            period="all",
            style="flat",
            label=None,
            color="4c1",
            label_color="555",
            logo_color="fff",
            logo=None,
            link=False,
            user_agent="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            x_forwarded_for="198.51.100.99",
            purpose=None,
            sec_purpose=None,
        )
        self.assertEqual(self.fake_redis.kv.get("hits:example.com/home"), "1")

        # 4. Prefetch header is ignored
        await route_handler(
            path="example.com/home.svg",
            request=req,
            period="all",
            style="flat",
            label=None,
            color="4c1",
            label_color="555",
            logo_color="fff",
            logo=None,
            link=False,
            user_agent="Mozilla/5.0",
            x_forwarded_for="198.51.100.100",
            purpose="prefetch",
            sec_purpose=None,
        )
        self.assertEqual(self.fake_redis.kv.get("hits:example.com/home"), "1")

    async def test_pixel_json_and_dashboard_endpoints(self):
        req_preview = DummyRequest(query_params={"preview": ""})
        png_resp = await route_handler(
            path="example.com/home.png",
            request=req_preview,
            period="all",
            style="flat",
            label=None,
            color="4c1",
            label_color="555",
            logo_color="fff",
            logo=None,
            link=False,
            user_agent="Mozilla/5.0",
            x_forwarded_for=None,
            purpose=None,
            sec_purpose=None,
        )
        self.assertEqual(png_resp.media_type, "image/png")
        self.assertTrue(png_resp.body.startswith(b"\x89PNG"))

        dash_resp = await route_handler(
            path="example.com/home",
            request=DummyRequest(),
            period="all",
            style="flat",
            label=None,
            color="4c1",
            label_color="555",
            logo_color="fff",
            logo=None,
            link=False,
            user_agent="Mozilla/5.0",
            x_forwarded_for=None,
            purpose=None,
            sec_purpose=None,
        )
        self.assertEqual(dash_resp.status_code, 200)
        self.assertIn(b"badgeBuilderForm", dash_resp.body)

    async def test_version_check_and_failure_backoff(self):
        database.http_client = DummyHttpClient(DummyHttpResponse(200, {"tag_name": "v9.9.9"}))
        info = await version.check_for_updates()
        self.assertTrue(info["has_update"])
        self.assertEqual(info["latest"], "9.9.9")

        self.fake_redis.kv.clear()
        database.http_client = DummyHttpClient(DummyHttpResponse(404))
        info_fail = await version.check_for_updates()
        self.assertFalse(info_fail["has_update"])
        self.assertEqual(self.fake_redis.kv.get("system:latest_version"), info_fail["current"])

    async def test_zero_dedupe_and_xff_spoof_resistance(self):
        req = DummyRequest()
        # Spoofing leftmost X-Forwarded-For does not bypass deduplication when rightmost IP is unchanged
        await tracker.record_visit("example.com/p", req, "Mozilla/5.0", "1.1.1.1, 198.51.100.5", None, None)
        await tracker.record_visit("example.com/p", req, "Mozilla/5.0", "2.2.2.2, 198.51.100.5", None, None)
        self.assertEqual(self.fake_redis.kv.get("hits:example.com/p"), "1")

        # DEDUPE_WINDOW_SECONDS=0 counts every visit without error
        orig_window = tracker.DEDUPE_WINDOW_SECONDS
        try:
            tracker.DEDUPE_WINDOW_SECONDS = 0
            await tracker.record_visit("example.com/p", req, "Mozilla/5.0", "198.51.100.5", None, None)
            self.assertEqual(self.fake_redis.kv.get("hits:example.com/p"), "2")
        finally:
            tracker.DEDUPE_WINDOW_SECONDS = orig_window


if __name__ == "__main__":
    unittest.main()
