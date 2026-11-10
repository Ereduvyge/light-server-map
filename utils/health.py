"""HTTP health checks: only a direct 2xx response is healthy."""

import asyncio
from urllib.parse import urlsplit, urlunsplit

import httpx
from loguru import logger

from db.models import Software


def healthcheck_url(software: Software) -> str:
    domain = software.domain.strip()
    if "://" not in domain:
        scheme = "https" if software.port == 443 else "http"
        domain = f"{scheme}://{domain}"
    url = urlsplit(domain)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError("domain must be an HTTP(S) origin or base URL without credentials")

    port = url.port or software.port
    host = f"[{url.hostname}]" if ":" in url.hostname else url.hostname
    path = f"{url.path.rstrip('/')}/{(software.health_check_path or '/').lstrip('/')}"
    # Keep the health path on the configured host; it cannot replace the origin.
    return urlunsplit((url.scheme, f"{host}:{port}", path, "", ""))


async def healthcheck(
    software: Software, client: httpx.AsyncClient, timeout: float = 5.0
) -> bool:
    try:
        url = healthcheck_url(software)
        # An outer deadline bounds the whole request, including slow headers.
        async with asyncio.timeout(timeout):
            async with client.stream(
                "GET", url, timeout=timeout, follow_redirects=False
            ) as response:
                return 200 <= response.status_code < 300
    except (httpx.HTTPError, TimeoutError, ValueError):
        logger.opt(exception=True).debug("HTTP check failed for software #{}", software.id)
        return False
