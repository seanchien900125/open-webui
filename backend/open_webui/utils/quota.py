"""Token usage quotas: look up a user's limits, enforce them, and record usage.

The check runs before a request is sent to the model and the tokens are charged
after the response ends, so this is a soft limit. A request that starts below the
limit may finish above it, and parallel requests can overshoot together. The next
request is refused.
"""

import logging
import time

from fastapi import HTTPException, Request
from open_webui.models.config import Config
from open_webui.models.groups import Groups
from open_webui.models.model_usage import ModelUsages
from open_webui.utils.audit import log_model_usage
from open_webui.utils.quota_policy import (
    UNLIMITED,
    WINDOW_DAILY,
    WINDOW_MONTHLY,
    QuotaLimits,
    first_exceeded,
    read_group_quota,
    resolve_limit,
    token_counts,
    window_bounds,
)
from open_webui.utils.response import normalize_usage

log = logging.getLogger(__name__)

QUOTA_CONFIG_KEYS = {
    'ENABLE_USAGE_QUOTA': 'usage.quota.enabled',
    'USAGE_QUOTA_DAILY_TOKENS': 'usage.quota.daily_tokens',
    'USAGE_QUOTA_MONTHLY_TOKENS': 'usage.quota.monthly_tokens',
    'USAGE_QUOTA_EXEMPT_ADMINS': 'usage.quota.exempt_admins',
}


async def get_quota_settings() -> dict:
    values = await Config.get_many(*QUOTA_CONFIG_KEYS.values())
    return {name: values.get(key) for name, key in QUOTA_CONFIG_KEYS.items()}


def is_exempt(user, settings: dict) -> bool:
    return user.role == 'admin' and bool(settings['USAGE_QUOTA_EXEMPT_ADMINS'])


async def get_user_limits(user, settings: dict) -> QuotaLimits:
    groups = await Groups.get_groups_by_member_id(user.id)
    group_quotas = [read_group_quota(group.data) for group in groups]
    return QuotaLimits(
        daily=resolve_limit((quota[WINDOW_DAILY] for quota in group_quotas), settings['USAGE_QUOTA_DAILY_TOKENS']),
        monthly=resolve_limit(
            (quota[WINDOW_MONTHLY] for quota in group_quotas), settings['USAGE_QUOTA_MONTHLY_TOKENS']
        ),
    )


async def get_quota_status(user, now: float | None = None) -> dict:
    """Limits, usage and reset times for one user. This is what the UI shows."""
    settings = await get_quota_settings()
    if not settings['ENABLE_USAGE_QUOTA'] or is_exempt(user, settings):
        return {'enabled': False}

    now = time.time() if now is None else now
    limits = await get_user_limits(user, settings)
    bounds = window_bounds(now)
    used = {
        window: await ModelUsages.sum_total_tokens(user.id, start)
        for window, (start, _) in bounds.items()
        if (limits.daily if window == WINDOW_DAILY else limits.monthly) != UNLIMITED
    }
    return {
        'enabled': True,
        'windows': {
            window: {
                'limit': limit,
                'used': used.get(window, 0),
                'resets_at': bounds[window][1],
            }
            for window, limit in ((WINDOW_DAILY, limits.daily), (WINDOW_MONTHLY, limits.monthly))
            if limit != UNLIMITED
        },
    }


async def enforce_usage_quota(user) -> None:
    """Raise HTTP 429 when the user has no tokens left in a window."""
    status = await get_quota_status(user)
    if not status['enabled']:
        return
    windows = status['windows']
    limits = QuotaLimits(
        daily=windows.get(WINDOW_DAILY, {}).get('limit', UNLIMITED),
        monthly=windows.get(WINDOW_MONTHLY, {}).get('limit', UNLIMITED),
    )
    exceeded = first_exceeded({window: info['used'] for window, info in windows.items()}, limits)
    if exceeded:
        info = windows[exceeded]
        raise HTTPException(
            status_code=429,
            detail=(
                f'You have reached your {exceeded} token quota '
                f'({info["used"]:,} of {info["limit"]:,} tokens used). '
                'It resets automatically; contact an administrator if you need more.'
            ),
            headers={'Retry-After': str(max(1, info['resets_at'] - int(time.time())))},
        )


async def track_model_usage(request: Request, user, model_id: str, usage: dict | None) -> None:
    """Audit-log a finished model call and, when quotas are on, charge its tokens to the user."""
    log_model_usage(request, user, model_id, usage)
    counts = token_counts(normalize_usage(usage or {}))
    if counts is None or counts[2] == 0:
        return
    try:
        # Quotas are opt-in: while they are off, usage costs no extra writes.
        if not (await get_quota_settings())['ENABLE_USAGE_QUOTA']:
            return
        await ModelUsages.record(user.id, model_id, *counts)
    except Exception:
        # Accounting must never break a response that already reached the user.
        log.exception('Failed to record model usage')
