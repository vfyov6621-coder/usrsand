"""sandusr configuration."""
import os
from dotenv import load_dotenv

load_dotenv()


def _parse_proxy(proxy_str: str):
    """Parse proxy string into pyrogram proxy dict.
    Formats:
      socks5://user:pass@host:port
      socks5://host:port
      http://user:pass@host:port
      http://host:port
    """
    if not proxy_str:
        return None
    try:
        from urllib.parse import urlparse
        p = urlparse(proxy_str)
        scheme = p.scheme.lower()
        if scheme not in ("socks5", "socks5h", "socks4", "http", "https"):
            scheme = "socks5"
        return {
            "scheme": scheme,
            "hostname": p.hostname,
            "port": p.port or 1080,
            "username": p.username or None,
            "password": p.password or None,
        }
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
    PROXY = _parse_proxy(os.environ.get("PROXY", ""))

    # Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
