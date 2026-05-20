"""sandusr configuration."""
import os
from dotenv import load_dotenv

load_dotenv()


def _parse_proxy(proxy_str: str):
    """Parse proxy string into pyrogram proxy dict.

    Formats:
      socks5://user:pass@host:port
      socks5://host:port
      socks4://host:port
      http://user:pass@host:port
      http://host:port

    Requires: pip install python-socks[asyncio]
    """
    if not proxy_str:
        return None
    try:
        from urllib.parse import urlparse
        p = urlparse(proxy_str)
        scheme = p.scheme.lower()

        # Normalize scheme for pyrogram
        if scheme in ("socks5h",):
            scheme = "socks5"  # socks5h = socks5 with remote DNS (pyrogram handles this)
        if scheme not in ("socks5", "socks4", "http"):
            scheme = "socks5"

        if not p.hostname or not p.port:
            return None

        result = {
            "scheme": scheme,
            "hostname": p.hostname,
            "port": p.port,
        }
        if p.username:
            result["username"] = p.username
        if p.password:
            result["password"] = p.password

        return result
    except Exception as e:
        import logging
        logging.getLogger("sandusr").error(f"Proxy parse error: {e}")
        return None


class Config:
    VERSION = "3.0"

    # Telegram
    API_ID = int(os.environ.get("API_ID", 0))
    API_HASH = os.environ.get("API_HASH", "")
    PHONE = os.environ.get("PHONE", "")
    SESSION_STRING = os.environ.get("SESSION_STRING", "")

    # Proxy (for blocked regions)
    # Set in .env: PROXY=socks5://user:pass@host:port
    # Requires: pip install python-socks[asyncio]
    PROXY = _parse_proxy(os.environ.get("PROXY", ""))

    # Force IPv4 (set to 0 to disable — useful if VPN supports IPv6)
    FORCE_IPV4 = os.environ.get("FORCE_IPV4", "1").lower() in ("1", "true", "yes")

    # Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
