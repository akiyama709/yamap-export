"""Login token handling for downloading your own GPS tracks.

YAMAP serves the ``points.xml`` GPS track only to a logged-in user. The web
app authenticates api.yamap.com requests with the header

    Authorization: Bearer token=<yamap_token>

where ``yamap_token`` is a cookie set when you sign in on yamap.com.

This module obtains that token in the least-surprising way it can and never
prints, logs, or writes it anywhere. The token is used only to talk to
api.yamap.com.
"""

from __future__ import annotations

import os
from typing import Optional


class TokenError(RuntimeError):
    pass


def _from_env() -> Optional[str]:
    return os.environ.get("YAMAP_TOKEN") or None


def _from_browser(browser: str = "auto") -> Optional[str]:
    """Read the yamap_token cookie from a local browser, if available.

    Requires the optional dependency ``browser-cookie3``. Returns ``None`` if
    it is not installed or no cookie is found.
    """
    try:
        import browser_cookie3 as bc3
    except ImportError:
        return None

    loaders = {
        "chrome": bc3.chrome,
        "firefox": bc3.firefox,
        "edge": bc3.edge,
        "brave": bc3.brave,
        "safari": getattr(bc3, "safari", None),
        "chromium": getattr(bc3, "chromium", None),
    }
    order = (
        [browser] if browser != "auto"
        else ["chrome", "brave", "edge", "chromium", "firefox", "safari"]
    )
    for name in order:
        fn = loaders.get(name)
        if fn is None:
            continue
        try:
            jar = fn(domain_name="yamap.com")
        except Exception:
            continue
        for c in jar:
            if c.name == "yamap_token" and c.value:
                return c.value
    return None


def resolve_token(explicit: Optional[str] = None,
                  browser: str = "auto") -> str:
    """Find a login token, or raise TokenError with guidance.

    Resolution order:
      1. an explicitly supplied token (``--token`` / function argument)
      2. the ``YAMAP_TOKEN`` environment variable
      3. the ``yamap_token`` cookie from a local browser you are signed in to
    """
    token = explicit or _from_env() or _from_browser(browser)
    if not token:
        raise TokenError(
            "No YAMAP login token found. Track download needs one of:\n"
            "  • pip install browser-cookie3, then sign in to yamap.com in "
            "Chrome/Firefox (the token is read automatically), or\n"
            "  • set the YAMAP_TOKEN environment variable, or\n"
            "  • pass --token <value> (copy the 'yamap_token' cookie from your "
            "browser's developer tools).\n"
            "The token is used only to fetch your own GPS tracks and is never "
            "stored or transmitted anywhere else."
        )
    return token


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer token={token}"}
