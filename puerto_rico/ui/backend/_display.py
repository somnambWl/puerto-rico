"""Shared good display data for the UI backend (design/06 — UI).

A single source of truth for how goods are named and valued in the browser, so
``labels.py`` (action strings) and ``catalog.py`` (the static ``GET /catalog``
payload) cannot drift apart. Pure display metadata — no rule is reimplemented
here; the base value is just the good's ordinal (corn 0 .. coffee 4).
"""

from __future__ import annotations

from puerto_rico.engine.enums import Good

#: Human-readable name per good.
GOOD_NAMES: dict[Good, str] = {
    Good.CORN: "Corn",
    Good.INDIGO: "Indigo",
    Good.SUGAR: "Sugar",
    Good.TOBACCO: "Tobacco",
    Good.COFFEE: "Coffee",
}

#: Base trading-house sell value per good (corn 0 .. coffee 4 = ``int(good)``).
GOOD_BASE_VALUE: dict[Good, int] = {good: int(good) for good in Good}
