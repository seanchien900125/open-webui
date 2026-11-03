"""Chat retention: delete chats nobody has touched for a configured number of days.

A pass builds a plan from the global settings and from group overrides stored in
``group.data.config.retention`` (``{"days": N, "hold": bool}``). A group on hold
protects its members completely, which is the legal-hold case.
"""

import logging
import time
from dataclasses import dataclass

from open_webui.events import EVENTS, publish_event
from open_webui.models.chats import Chats
from open_webui.models.config import Config
from open_webui.models.groups import Groups
from open_webui.tasks import stop_item_tasks
from open_webui.utils.retention_policy import (
    RetentionPolicy,
    as_days,
    cutoff_timestamp,
    read_group_retention,
    resolve_policy,
)

log = logging.getLogger(__name__)

RETENTION_CONFIG_KEYS = {
    'ENABLE_CHAT_RETENTION': 'retention.chat.enabled',
    'CHAT_RETENTION_DAYS': 'retention.chat.days',
    'CHAT_RETENTION_KEEP_PINNED': 'retention.chat.keep_pinned',
    'CHAT_RETENTION_KEEP_ARCHIVED': 'retention.chat.keep_archived',
}

# Chats removed by one pass. The next pass continues, so a large backlog never blocks the scheduler.
MAX_DELETIONS_PER_PASS = 500
BATCH_SIZE = 100


async def get_retention_settings() -> dict:
    values = await Config.get_many(*RETENTION_CONFIG_KEYS.values())
    return {name: values.get(key) for name, key in RETENTION_CONFIG_KEYS.items()}


@dataclass(frozen=True)
class Query:
    """One selection of expired chats: a retention period applied to a set of users."""

    days: int
    user_ids: list[str] | None = None  # only these users
    exclude_user_ids: list[str] | None = None  # everyone except these users


async def build_plan(default_days: int) -> list[Query]:
    """Queries that together cover every user whose chats may expire.

    Users in a group with a retention rule get their own resolved policy; everyone
    else follows ``default_days``.
    """
    groups = [
        (group.id, rule)
        for group in await Groups.get_all_groups()
        if (rule := read_group_retention(group.data)) is not None
    ]
    members = await Groups.get_group_user_ids_by_ids([group_id for group_id, _ in groups], include_inherited=True)
    rules_by_user: dict[str, list[dict]] = {}
    for group_id, rule in groups:
        for user_id in members.get(group_id, []):
            rules_by_user.setdefault(user_id, []).append(rule)

    policies: dict[str, RetentionPolicy] = {
        user_id: resolve_policy(rules, default_days) for user_id, rules in rules_by_user.items()
    }
    plan = []
    if default_days > 0:
        plan.append(Query(days=default_days, exclude_user_ids=list(policies)))
    by_days: dict[int, list[str]] = {}
    for user_id, policy in policies.items():
        if policy.deletes:
            by_days.setdefault(policy.days, []).append(user_id)
    plan.extend(Query(days=days, user_ids=user_ids) for days, user_ids in sorted(by_days.items()))
    return plan


def _filters(settings: dict) -> dict:
    return {
        'keep_pinned': bool(settings['CHAT_RETENTION_KEEP_PINNED']),
        'keep_archived': bool(settings['CHAT_RETENTION_KEEP_ARCHIVED']),
    }


async def count_expired(settings: dict, now: float | None = None) -> int:
    """How many chats the given settings would delete right now. Deletes nothing."""
    now = time.time() if now is None else now
    total = 0
    for query in await build_plan(as_days(settings['CHAT_RETENTION_DAYS']) or 0):
        total += await Chats.count_expired_chats(
            cutoff_timestamp(now, query.days),
            user_ids=query.user_ids,
            exclude_user_ids=query.exclude_user_ids,
            **_filters(settings),
        )
    return total


async def delete_chat(app, chat_id: str, user_id: str) -> bool:
    """Delete one chat the way the manual delete does: tasks, child chats, tags, then the rows."""
    chat = await Chats.get_chat_by_id(chat_id)
    if chat is None:
        return False
    await stop_item_tasks(app.state.redis, chat_id)
    await Chats.delete_orphan_tags_for_user(chat.meta.get('tags', []), user_id, threshold=1)
    for child_id in await Chats.get_internal_chat_ids_by_parent_id(chat_id, user_id):
        await stop_item_tasks(app.state.redis, child_id)
        await Chats.delete_chat_by_id_and_user_id(child_id, user_id)
    return await Chats.delete_chat_by_id_and_user_id(chat_id, user_id)


async def purge_expired_chats(app, now: float | None = None) -> int:
    """Delete expired chats, at most ``MAX_DELETIONS_PER_PASS``. Returns how many were deleted."""
    settings = await get_retention_settings()
    if not settings['ENABLE_CHAT_RETENTION']:
        return 0
    now = time.time() if now is None else now
    deleted = 0
    for query in await build_plan(as_days(settings['CHAT_RETENTION_DAYS']) or 0):
        cutoff = cutoff_timestamp(now, query.days)
        while deleted < MAX_DELETIONS_PER_PASS:
            batch = await Chats.get_expired_chats(
                cutoff,
                user_ids=query.user_ids,
                exclude_user_ids=query.exclude_user_ids,
                limit=min(BATCH_SIZE, MAX_DELETIONS_PER_PASS - deleted),
                **_filters(settings),
            )
            if not batch:
                break
            removed = 0
            for chat_id, user_id in batch:
                try:
                    if await delete_chat(app, chat_id, user_id):
                        removed += 1
                        await publish_event(
                            app,
                            EVENTS.CHAT_DELETED,
                            source='retention',
                            subject_id=chat_id,
                            data={'owner_id': user_id, 'reason': 'retention', 'retention_days': query.days},
                        )
                except Exception:
                    log.exception('Retention: failed to delete chat %s', chat_id)
            deleted += removed
            if removed == 0:
                # Nothing in this batch could be deleted; looping again would select the same rows.
                break
    if deleted:
        log.info('Retention: deleted %s expired chat(s)', deleted)
    return deleted
