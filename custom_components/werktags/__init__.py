"""Werktags — workdays per person for Home Assistant.

Stage 1: rules only (``rules.py``). The Home Assistant setup follows in stage 3;
until then this package imports without Home Assistant so the rules can be
tested on their own.
"""
from __future__ import annotations

from .const import DOMAIN

__all__ = ["DOMAIN"]
