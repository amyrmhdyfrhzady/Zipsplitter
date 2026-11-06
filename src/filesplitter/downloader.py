from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import requests


class UnsafeURLError(ValueError):
    pass


def validate_public_http_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError("Only HTTP and HTTPS URLs are supported")
    if not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeURLError("URL host is missing or URL user information is not allowed")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeURLError("Invalid URL port") from exc
    if port is not None and not (1 <= port <= 65535):
        raise UnsafeURLError("Invalid URL port")

    try:
        literal_ip = ipaddress.ip_address(parsed.hostname)
        addresses = [literal_ip]
    except ValueError:
        try:
            records = socket.getaddrinfo(parsed.hostname, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise UnsafeURLError(f"Could not resolve URL host: {parsed.hostname}") from exc
        addresses = [ipaddress.ip_address(record[4][0]) for record in records]
    if not addresses or any(not address.is_global for address in addresses):
        raise UnsafeURLError("URLs resolving to private, local, link-local, or reserved IP addresses are blocked")


def download_url(url: str, destination: str, max_bytes: int) -> int:
    current_url = url
    session = requests.Session()
    session.trust_env = False
    headers = {"User-Agent": "FileSplitter-API/1.0", "Accept": "*/*"}

    for redirect_count in range(6):
        validate_public_http_url(current_url)
        try:
            request_context = session.get(current_url, headers=headers, stream=True, timeout=(20, 90), allow_redirects=False)
        except requests.RequestException as exc:
            # Do not echo full URLs: signed query strings can contain temporary credentials.
            raise RuntimeError(f"Could not connect to the input host ({type(exc).__name__})") from None
        with request_context as response:
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise RuntimeError("Download server returned a redirect without a Location header")
                if redirect_count == 5:
                    raise RuntimeError("Too many redirects while downloading the input")
                current_url = urljoin(current_url, location)
                continue
            if response.status_code >= 400:
                raise RuntimeError(f"Input server returned HTTP {response.status_code}")
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > max_bytes:
                raise ValueError(f"Input exceeds the configured maximum of {max_bytes} bytes")
            total = 0
            with open(destination, "wb") as output:
                for block in response.iter_content(chunk_size=1024 * 1024):
                    if not block:
                        continue
                    total += len(block)
                    if total > max_bytes:
                        raise ValueError(f"Input exceeds the configured maximum of {max_bytes} bytes")
                    output.write(block)
            if total == 0:
                raise ValueError("The downloaded file is empty")
            return total
    raise RuntimeError("Could not download input")
