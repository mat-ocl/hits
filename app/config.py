import fnmatch
import os
import re
import secrets

CURRENT_VERSION = os.getenv("APP_VERSION", "0.1.8")
GITHUB_REPO = "mat-ocl/hits"
VERSION_CHECK_CACHE_SECONDS = 43200  # 12 hours
VERSION_CHECK_FAILURE_CACHE_SECONDS = 3600  # 1 hour backoff on failed checks

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DEDUPE_WINDOW_SECONDS = int(os.getenv("DEDUPE_WINDOW_SECONDS", "600"))
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "true").lower() in ("1", "true", "yes")
HASH_SALT = os.getenv("HASH_SALT") or secrets.token_hex(32)
ALLOWED_DOMAINS = [
    d.strip().lower()
    for d in os.getenv("ALLOWED_DOMAINS", "*").split(",")
    if d.strip()
]

# Validates path format (e.g., domain.tld/page)
VALID_PATH_PATTERN = re.compile(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/[a-zA-Z0-9._~-]+)*$")


def is_domain_allowed(page_key: str) -> bool:
    if not ALLOWED_DOMAINS or "*" in ALLOWED_DOMAINS:
        return True
    domain = page_key.split("/", 1)[0].lower()
    for pattern in ALLOWED_DOMAINS:
        if pattern.startswith("*."):
            base = pattern[2:]
            if domain == base or domain.endswith(f".{base}"):
                return True
        elif fnmatch.fnmatch(domain, pattern):
            return True
    return False


# Standard 1x1 transparent GIF bytes
TRANSPARENT_1X1_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)

# Standard 1x1 transparent PNG bytes
TRANSPARENT_1X1_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
