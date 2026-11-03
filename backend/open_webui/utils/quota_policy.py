"""Pure rules for token usage quotas.

Everything here is deterministic and uses only the standard library, so the rules
can be unit tested without a database or the rest of the backend.

Limits are token counts per window. ``0`` means unlimited.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

UNLIMITED = 0

WINDOW_DAILY = 'daily'
WINDOW_MONTHLY = 'monthly'


@dataclass(frozen=True)
class QuotaLimits:
    daily: int = UNLIMITED
    monthly: int = UNLIMITED

    def is_unlimited(self) -> bool:
        return self.daily == UNLIMITED and self.monthly == UNLIMITED


def as_limit(value: Any) -> int | None:
    """A non-negative whole number, or ``None`` when the value is unset or invalid."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def window_bounds(now: float) -> dict[str, tuple[int, int]]:
    """Start (inclusive) and reset (exclusive) of the current day and month, in server-local time."""
    local = dt.datetime.fromtimestamp(now)
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)
    next_month = (month_start + dt.timedelta(days=32)).replace(day=1)
    return {
        WINDOW_DAILY: (int(day_start.timestamp()), int((day_start + dt.timedelta(days=1)).timestamp())),
        WINDOW_MONTHLY: (int(month_start.timestamp()), int(next_month.timestamp())),
    }


def resolve_limit(group_values: Iterable[Any], default: int) -> int:
    """The limit that applies to a user for one window.

    Groups win over the global default. Several groups follow the most permissive
    rule used for group permissions: ``0`` (unlimited) beats any number, and
    otherwise the highest number applies. Without any group value, ``default`` applies.
    """
    values = [limit for limit in (as_limit(value) for value in group_values) if limit is not None]
    if not values:
        return as_limit(default) or UNLIMITED
    if UNLIMITED in values:
        return UNLIMITED
    return max(values)


def read_group_quota(group_data: dict | None) -> dict[str, int | None]:
    """Daily and monthly limits stored in a group's ``data.config.usage_quota``."""
    quota = ((group_data or {}).get('config') or {}).get('usage_quota') or {}
    if not isinstance(quota, dict):
        return {WINDOW_DAILY: None, WINDOW_MONTHLY: None}
    return {
        WINDOW_DAILY: as_limit(quota.get('daily_tokens')),
        WINDOW_MONTHLY: as_limit(quota.get('monthly_tokens')),
    }


def token_counts(usage: dict | None) -> tuple[int, int, int] | None:
    """``(input, output, total)`` from a normalized usage dict, or ``None`` if it reports nothing."""
    if not isinstance(usage, dict):
        return None
    input_tokens = as_limit(usage.get('input_tokens'))
    output_tokens = as_limit(usage.get('output_tokens'))
    total = as_limit(usage.get('total_tokens'))
    if total is None and (input_tokens is not None or output_tokens is not None):
        total = (input_tokens or 0) + (output_tokens or 0)
    if total is None:
        return None
    return input_tokens or 0, output_tokens or 0, total


def first_exceeded(used: dict[str, int], limits: QuotaLimits) -> str | None:
    """The first window whose limit is reached, daily before monthly, or ``None``."""
    for window, limit in ((WINDOW_DAILY, limits.daily), (WINDOW_MONTHLY, limits.monthly)):
        if limit != UNLIMITED and used.get(window, 0) >= limit:
            return window
    return None
