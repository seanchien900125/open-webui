"""Guardrails for chat input: mask personal data and flag or refuse prompt injection.

The rules live in ``guardrails_policy``. This module reads the admin settings, applies
the rules to the messages of a chat request, and reports what happened. The matched
text is never logged or published, only kinds and counts.

Stored chats keep what the user typed. Masking changes only the copy that is sent to
the model, so the user still sees their own message unchanged.
"""

import logging
from dataclasses import replace

from fastapi import HTTPException, Request
from open_webui.events import EVENTS, publish_event
from open_webui.models.config import Config
from open_webui.utils.guardrails_policy import (
    ACTION_MASK,
    ACTION_OFF,
    INJECTION_ACTIONS,
    PII_ACTIONS,
    GuardrailOutcome,
    GuardrailSettings,
    apply_guardrails,
    clean_action,
    clean_pii_kinds,
)

log = logging.getLogger(__name__)

GUARDRAIL_CONFIG_KEYS = {
    'ENABLE_GUARDRAILS': 'guardrails.enabled',
    'GUARDRAILS_PII_ACTION': 'guardrails.pii.action',
    'GUARDRAILS_PII_KINDS': 'guardrails.pii.kinds',
    'GUARDRAILS_INJECTION_ACTION': 'guardrails.injection.action',
    'GUARDRAILS_EXEMPT_ADMINS': 'guardrails.exempt_admins',
}

BLOCK_MESSAGES = {
    'pii': 'Your message was not sent because it appears to contain personal or sensitive data. '
    'Remove it and try again.',
    'injection': 'Your message was not sent because it matched a prompt injection rule.',
}


async def get_guardrail_settings() -> dict:
    values = await Config.get_many(*GUARDRAIL_CONFIG_KEYS.values())
    return {name: values.get(key) for name, key in GUARDRAIL_CONFIG_KEYS.items()}


def build_settings(values: dict) -> GuardrailSettings:
    """Policy settings from stored values; anything unusable falls back to the safe default."""
    return GuardrailSettings(
        enabled=bool(values.get('ENABLE_GUARDRAILS')),
        pii_action=clean_action(values.get('GUARDRAILS_PII_ACTION'), PII_ACTIONS, 'mask'),
        pii_kinds=clean_pii_kinds(values.get('GUARDRAILS_PII_KINDS')),
        injection_action=clean_action(values.get('GUARDRAILS_INJECTION_ACTION'), INJECTION_ACTIONS, 'log'),
        exempt_admins=bool(values.get('GUARDRAILS_EXEMPT_ADMINS')),
    )


def outcome_data(outcome: GuardrailOutcome, action: str) -> dict:
    return {
        'action': action,
        'pii': outcome.pii,
        'injection': outcome.injection,
    }


async def enforce_guardrails(request: Request, user, form_data: dict, metadata: dict | None = None) -> dict:
    """Apply the guardrails to ``form_data['messages']`` and return the updated form data.

    Raises ``HTTPException`` (400) when the newest user message must be refused.
    """
    settings = build_settings(await get_guardrail_settings())
    if not settings.active or (settings.exempt_admins and getattr(user, 'role', None) == 'admin'):
        return form_data

    messages = form_data.get('messages')
    if not isinstance(messages, list):
        return form_data

    result, outcome = apply_guardrails(messages, settings)
    if not outcome.triggered:
        return form_data

    if outcome.blocked:
        action = 'blocked'
    elif outcome.masked:
        action = 'masked'
    else:
        action = 'logged'

    chat_id = (metadata or {}).get('chat_id') or None
    log.warning(
        'guardrail %s user=%s chat=%s pii=%s injection=%s',
        action,
        getattr(user, 'id', None),
        chat_id,
        outcome.pii,
        outcome.injection,
    )
    try:
        await publish_event(
            request,
            EVENTS.GUARDRAIL_TRIGGERED,
            actor=user,
            subject_id=chat_id,
            subject_type='chat' if chat_id else None,
            data={'user_id': getattr(user, 'id', None), 'chat_id': chat_id, **outcome_data(outcome, action)},
        )
    except Exception:
        log.exception('Failed to publish guardrail event')

    if outcome.blocked:
        raise HTTPException(status_code=400, detail=BLOCK_MESSAGES[outcome.blocked])

    form_data['messages'] = result
    return form_data


async def mask_messages_for_tasks(user, messages: list[dict]) -> list[dict]:
    """Messages for background tasks (title, tags, follow-ups) with personal data masked.

    Those tasks read the stored text again, which still holds what the user typed. Only the
    ``mask`` action rewrites anything: a message that was refused never gets this far, and
    ``log`` is meant to leave text untouched. Nothing is reported, the request already was.
    """
    settings = build_settings(await get_guardrail_settings())
    if (
        not settings.active
        or settings.pii_action != ACTION_MASK
        or (settings.exempt_admins and getattr(user, 'role', None) == 'admin')
    ):
        return messages
    masked, _ = apply_guardrails(messages, replace(settings, injection_action=ACTION_OFF))
    return masked
