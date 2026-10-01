"""Serve the dashboard cards from the integration (HACS version only).

The built JavaScript lives in ``www/`` next to this file. It is served under a
URL that carries a hash of its content (browsers cache it for a month) and
announced to the frontend, so nobody has to add a Lovelace resource by hand.
A browser that was open before the integration was set up must be reloaded
once: the list of scripts is part of the page itself. The core version of the integration would not ship this
module; the cards would then come from their own repository.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http.server import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
CARDS_FILE = "werktags-cards.js"
URL_BASE = f"/{DOMAIN}_static"
_REGISTERED_KEY = f"{DOMAIN}_frontend_registered"


async def async_register(hass: HomeAssistant) -> None:
    """Register the static path and the script URL once per Home Assistant run."""
    if hass.data.get(_REGISTERED_KEY):
        return
    if "frontend" not in hass.config.components or "http" not in hass.config.components:
        _LOGGER.debug("Frontend not loaded — cards not served")
        return
    www = Path(__file__).parent / "www"
    if not (www / CARDS_FILE).is_file():
        _LOGGER.debug("No %s in %s — cards not served", CARDS_FILE, www)
        return
    digest = await hass.async_add_executor_job(_content_hash, www / CARDS_FILE)
    await hass.http.async_register_static_paths([StaticPathConfig(URL_BASE, str(www), cache_headers=True)])
    add_extra_js_url(hass, f"{URL_BASE}/{CARDS_FILE}?v={digest}")
    hass.data[_REGISTERED_KEY] = True


def _content_hash(path: Path) -> str:
    """Eight hex digits of the bundle's SHA-256: a new build gets a new URL and bypasses old caches."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]

