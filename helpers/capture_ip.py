# utils/ip.py  (or wherever you keep helpers)
from flask import request

def client_ip() -> str:
    """
    Return the browser’s public IP, even when requests come through Cloudflare
    or another proxy. Falls back gracefully if the header is absent.
    """
    return (
        request.headers.get("CF-Connecting-IP")       # Cloudflare
        or request.headers.get("X-Forwarded-For", "") # generic proxy chain
            .split(",")[0].strip()
        or request.remote_addr                        # direct hit
    )
