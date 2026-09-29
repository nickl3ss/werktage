"""Serve the dashboard cards from the integration (HACS version only).

The built JavaScript lives in ``www/`` next to this file. It is served under a
versioned URL and announced to the frontend, so nobody has to add a Lovelace
resource by hand. The core version of the integration would not ship this
module; the cards would then come from their own repository.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http.server import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN, VERSION

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
    await hass.http.async_register_static_paths([StaticPathConfig(URL_BASE, str(www), cache_headers=True)])
    add_extra_js_url(hass, f"{URL_BASE}/{CARDS_FILE}?v={VERSION}")
    hass.data[_REGISTERED_KEY] = True
