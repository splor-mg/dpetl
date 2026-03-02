import os
import socket
from urllib.parse import urlparse

import socks
from dotenv import find_dotenv, load_dotenv


def force_ipv4():
    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
        return original_getaddrinfo(
            host,
            port,
            socket.AF_INET,
            type,
            proto,
            flags,
        )

    socket.getaddrinfo = getaddrinfo_ipv4


def configure_proxy_from_env():
    load_dotenv(find_dotenv(usecwd=True))

    force_ipv4()

    proxy_url = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("http_proxy")
    )

    if not proxy_url:
        return

    parsed = urlparse(proxy_url)

    proxy_type_map = {
        "http": socks.HTTP,
        "socks5": socks.SOCKS5,
    }

    proxy_type = proxy_type_map.get(parsed.scheme.lower(), socks.HTTP)

    socks.set_default_proxy(
        proxy_type,
        parsed.hostname,
        parsed.port,
        username=parsed.username,
        password=parsed.password,
    )

    socket.socket = socks.socksocket
