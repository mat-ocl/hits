# hits

Lightweight, self-hosted website visitor & hit counter service built with **FastAPI** and **Redis**.

Generate customizable shields.io-style SVG badges, 1×1 tracking pixels, JSON analytics API responses, and an interactive dark-mode analytics dashboard for any domain or page.

---

## Features

- **5 Badge Styles:** `flat`, `flat-square`, `plastic`, `for-the-badge`, and `social`
- **Simple Icons Support:** Embed any [Simple Icons](https://simpleicons.org/) logo via `?logo=github` (cached in Redis & memory)
- **Time-Window Metrics:** Display `all`-time, `today`, `7d` (weekly), or `30d` (monthly) hit counts
- **Bot & Prefetch Filtering:** Automatically ignores crawlers (`crawlerdetect`) and browser `prefetch`/`prerender` requests
- **Privacy-Preserving Deduplication:** Salted, daily-rotating SHA-256 visitor hashes with a configurable deduplication window
- **Domain Allowlist:** Restrict tracking to your own domains (`ALLOWED_DOMAINS=example.com,*.example.com`)
- **Interactive Dashboard & Badge Builder:** Built-in 30-day Chart.js analytics page with a live badge customizer and one-click embed code generator

---

## Quick Start

### Production (`ghcr.io/mat-ocl/hits:latest`)

```bash
docker compose up -d
```

### Local Test Build

```bash
docker compose -f ./compose-testbuild.yaml up --build -d
```

Once running, visit `http://localhost:8000` for the service landing page or `http://localhost:8000/example.com` to open the analytics dashboard and badge builder for `example.com`.

---

## Endpoints

Replace `{page}` with `{domain.tld}` or `{domain.tld}/{subpath}` (e.g. `example.com/blog/post-1`):

| Endpoint | Description | Increments Counter? |
| :--- | :--- | :--- |
| `GET /{page}.svg` | Renders a customizable SVG hit counter badge | Yes (unless `?preview` or `?no_count`) |
| `GET /{page}.gif` | Returns a 1×1 transparent GIF tracking pixel | Yes (unless `?preview` or `?no_count`) |
| `GET /{page}.png` | Returns a 1×1 transparent PNG tracking pixel | Yes (unless `?preview` or `?no_count`) |
| `GET /{page}.json` | Returns JSON metrics (`total`, `today`, `last_7_days`, `last_30_days`, `daily`) | Yes (unless `?preview` or `?no_count`) |
| `GET /{page}` | Renders the HTML analytics dashboard & interactive Badge Builder | No |
| `GET /health` | Redis connectivity healthcheck (`200 OK` or `503 Service Unavailable`) | No |

---

## Badge Customization (`/{page}.svg`)

Customize the SVG badge using query parameters:

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `style` | `flat` | Badge style: `flat`, `flat-square`, `plastic`, `for-the-badge`, or `social` |
| `period` | `all` | Counter window: `all`, `today`, `7d` (`weekly`), or `30d` (`monthly`) |
| `label` | *period name* | Custom left-side label text (defaults to `hits`, `today`, `7d`, or `30d`) |
| `color` | `4c1` | Right-side background color (hex code like `38bdf8` or named color like `brightgreen`, `blue`, `orange`) |
| `labelColor` | `555` | Left-side background color (hex code or named color) |
| `logo` | *none* | [Simple Icons](https://simpleicons.org/) slug (e.g. `github`, `python`, `docker`) |
| `logoColor` | `fff` | Icon fill color (hex code or named color) |
| `link` | `false` | Wrap the internal SVG in an `<a href="/{page}">` link (`?link=true` or `?link`) |
| `preview` / `no_count` | *none* | Render the badge (or `.json` / `.gif` / `.png`) without incrementing the hit counter |

### Embed Examples

**Markdown:**
```markdown
[![Hits](https://hits.example.com/mysite.com/blog.svg?style=flat-square&color=38bdf8&logo=rss)](https://hits.example.com/mysite.com/blog)
```

**HTML Badge:**
```html
<a href="https://hits.example.com/mysite.com/blog">
  <img src="https://hits.example.com/mysite.com/blog.svg?period=7d&label=weekly+views" alt="Hits">
</a>
```

**Silent 1×1 Tracking Pixel:**
```html
<img src="https://hits.example.com/mysite.com/blog.gif" alt="" width="1" height="1" style="display:none">
```

---

## Configuration (Environment Variables)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `DEDUPE_WINDOW_SECONDS` | `600` | Seconds before a repeat visit from the same IP to the same page is counted again |
| `ALLOWED_DOMAINS` | `*` | Comma-separated allowlist of trackable domains (supports exact `example.com` and wildcard `*.example.com`) |
| `TRUST_PROXY_HEADERS` | `true` | Whether to read the client IP from `X-Forwarded-For` when behind a reverse proxy |
| `HASH_SALT` | *random 256-bit hex* | Secret salt mixed into daily-rotating visitor IP hashes |
| `APP_VERSION` | `0.1.4-dev` | Application version string displayed in the dashboard footer |

---

## Development & Testing

Install dependencies and run the test suite:

```bash
pip install -r requirements.txt pytest
pytest -v
```
