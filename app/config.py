import os
import re

CURRENT_VERSION = "0.1.4-dev"
GITHUB_REPO = "mat-ocl/hits"
VERSION_CHECK_CACHE_SECONDS = 43200  # 12 hours

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DEDUPE_WINDOW_SECONDS = int(os.getenv("DEDUPE_WINDOW_SECONDS", "600"))

# Validates path format (e.g., domain.tld/page)
VALID_PATH_PATTERN = re.compile(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/[a-zA-Z0-9._~-]+)*$")

# Standard 1x1 transparent GIF bytes
TRANSPARENT_1X1_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)