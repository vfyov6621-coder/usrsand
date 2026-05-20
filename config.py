"""sandusr configuration."""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    VERSION = "3.0"

    # Telegram
    API_ID = int(os.environ.get("API_ID", 0))
    API_HASH = os.environ.get("API_HASH", "")
    PHONE = os.environ.get("PHONE", "")
    SESSION_STRING = os.environ.get("SESSION_STRING", "")

    # Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
