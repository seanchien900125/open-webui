"""Pure rules for chat retention.

Deterministic and standard-library only, so the rules can be unit tested without a
database. Retention is a number of days; ``0`` means keep forever.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

KEEP_FOREVER = 0
SECONDS_PER_DAY = 86400


@dataclass(frozen=True)
class RetentionPolicy:
    """What applies to one user. ``hold`` is a legal hold: nothing of theirs is deleted."""

    days: int = KEEP_FOREVER
    hold: bool = False

    @property
    def deletes(self) -> bool:
        return not self.hold and self.days != KEEP_FOREVER


def as_days(value: Any) -> int | None:
    """A non-negative whole number of days, or ``None`` when unset or invalid."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def read_group_retention(group_data: dict | None) -> dict[str, Any] | None:
    """A group's ``data.config.retention``, or ``None`` when the group sets nothing."""
    retention = ((group_data or {}).get('config') or {}).get('retention')
    if not isinstance(retention, dict):
        return None
    days = as_days(retention.get('days'))
    hold = retention.get('hold') is True
    if days is None and not hold:
        return None
    return {'days': days, 'hold': hold}


def resolve_policy(group_policies: Iterable[dict[str, Any] | None], default_days: Any) -> RetentionPolicy:
    """The policy for a user in the given groups.

    Deleting data is the risky direction, so conflicts resolve toward keeping it:
    any group on hold protects the user, a group set to keep forever beats any
    number, and otherwise the longest retention wins. Without a group value the
    global default applies.
    """
    policies = [policy for policy in group_policies if policy]
    if any(policy['hold'] for policy in policies):
        return RetentionPolicy(days=as_days(default_days) or KEEP_FOREVER, hold=True)
    values = [policy['days'] for policy in policies if policy['days'] is not None]
    if not values:
        return RetentionPolicy(days=as_days(default_days) or KEEP_FOREVER)
    if KEEP_FOREVER in values:
        return RetentionPolicy(days=KEEP_FOREVER)
    return RetentionPolicy(days=max(values))


def cutoff_timestamp(now: float, days: int) -> int:
    """Chats last updated before this epoch second have outlived ``days``."""
    return int(now) - days * SECONDS_PER_DAY
