"""
Shared utilities for sandusr scripts.
Import: from scripts._utils import safe_edit
"""

import os
import sys

# Ensure project root is in sys.path
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)


async def safe_edit(message, text, **kwargs):
    """
    Safe edit_text with fallback to reply.
    In channels without edit rights, edit_text throws ChatWriteForbidden.
    This tries edit_text first, then falls back to reply.
    """
    try:
        return await message.edit_text(text, **kwargs)
    except Exception:
        try:
            return await message.reply(text, quote=False, **kwargs)
        except Exception:
            pass
    return None
