"""Shared helpers for the Infomaniak DDNS integration."""
from __future__ import annotations

import re
from urllib.parse import urlparse

IPV4_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
IP_REGEX = re.compile(r"(\d{1,3}\.){3}\d{1,3}")


def is_valid_ipv4(ip: str) -> bool:
    """Return True if the string is a valid IPv4 address."""
    if not IPV4_RE.match(ip):
        return False
    return all(0 <= int(octet) <= 255 for octet in ip.split("."))


def is_valid_service_url(url: str) -> bool:
    """Return True if the URL has an http(s) scheme and a valid netloc."""
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)
