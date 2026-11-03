from fastapi import APIRouter, Depends, HTTPException, Request
from open_webui.events import EVENTS, publish_event
from open_webui.models.config import Config
from open_webui.utils.auth import get_admin_user
from open_webui.utils.guardrails import GUARDRAIL_CONFIG_KEYS, build_settings, get_guardrail_settings
from open_webui.utils.guardrails_policy import (
    INJECTION_ACTIONS,
    PII_ACTIONS,
    PII_KINDS,
    apply_guardrails,
)
from pydantic import BaseModel, Field, field_validator

router = APIRouter()


class GuardrailsConfigForm(BaseModel):
    ENABLE_GUARDRAILS: bool | None = None
    GUARDRAILS_PII_ACTION: str | None = None
    GUARDRAILS_PII_KINDS: list[str] | None = None
    GUARDRAILS_INJECTION_ACTION: str | None = None
    GUARDRAILS_EXEMPT_ADMINS: bool | None = None

    @field_validator('GUARDRAILS_PII_ACTION')
    @classmethod
    def validate_pii_action(cls, value):
        if value is not None and value not in PII_ACTIONS:
            raise ValueError(f'must be one of {", ".join(PII_ACTIONS)}')
        return value

    @field_validator('GUARDRAILS_INJECTION_ACTION')
    @classmethod
    def validate_injection_action(cls, value):
        if value is not None and value not in INJECTION_ACTIONS:
            raise ValueError(f'must be one of {", ".join(INJECTION_ACTIONS)}')
        return value

    @field_validator('GUARDRAILS_PII_KINDS')
    @classmethod
    def validate_pii_kinds(cls, value):
        if value is not None:
            unknown = [kind for kind in value if kind not in PII_KINDS]
            if unknown:
                raise ValueError(f'unknown kinds: {", ".join(unknown)}')
        return value


class GuardrailsTestForm(BaseModel):
    text: str = Field(max_length=20000)


@router.get('/config', response_model=GuardrailsConfigForm)
async def get_guardrails_config(user=Depends(get_admin_user)):
    return await get_guardrail_settings()


@router.post('/config', response_model=GuardrailsConfigForm)
async def set_guardrails_config(request: Request, form_data: GuardrailsConfigForm, user=Depends(get_admin_user)):
    values = form_data.model_dump(exclude_unset=True)
    updates = {GUARDRAIL_CONFIG_KEYS[name]: value for name, value in values.items() if value is not None}
    await Config.upsert(updates)
    await publish_event(
        request,
        EVENTS.CONFIG_UPDATED,
        actor=user,
        subject_id='guardrails',
        subject_type='config',
        data={'keys': list(updates)},
    )
    return await get_guardrail_settings()


@router.post('/test')
async def test_guardrails(form_data: GuardrailsTestForm, user=Depends(get_admin_user)):
    """Run a sample message through the saved settings. Nothing is stored or sent to a model.

    Reports what a real request would do, ignoring the on/off switch so rules can be tried
    before they are enabled.
    """
    settings = build_settings({**await get_guardrail_settings(), 'ENABLE_GUARDRAILS': True})
    if not settings.active:
        raise HTTPException(status_code=400, detail='Both guardrail actions are off, so there is nothing to test.')

    messages, outcome = apply_guardrails([{'role': 'user', 'content': form_data.text}], settings)
    action = (
        'blocked' if outcome.blocked else 'masked' if outcome.masked else 'logged' if outcome.triggered else 'clean'
    )
    return {
        'action': action,
        'blocked_by': outcome.blocked,
        'pii': outcome.pii,
        'injection': outcome.injection,
        'text': messages[0]['content'],
    }
