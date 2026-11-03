from fastapi import APIRouter, Depends, Request
from open_webui.events import EVENTS, publish_event
from open_webui.models.config import Config
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.quota import QUOTA_CONFIG_KEYS, get_quota_settings, get_quota_status
from pydantic import BaseModel, Field

router = APIRouter()


############################
# Quota status (current user)
############################


@router.get('/quota')
async def get_my_quota(user=Depends(get_verified_user)):
    """Limits, usage and reset times for the signed-in user."""
    return await get_quota_status(user)


############################
# Quota settings (admin)
############################


class QuotaConfigForm(BaseModel):
    ENABLE_USAGE_QUOTA: bool | None = None
    USAGE_QUOTA_DAILY_TOKENS: int | None = Field(default=None, ge=0)
    USAGE_QUOTA_MONTHLY_TOKENS: int | None = Field(default=None, ge=0)
    USAGE_QUOTA_EXEMPT_ADMINS: bool | None = None


@router.get('/quota/config', response_model=QuotaConfigForm)
async def get_quota_config(user=Depends(get_admin_user)):
    return await get_quota_settings()


@router.post('/quota/config', response_model=QuotaConfigForm)
async def set_quota_config(request: Request, form_data: QuotaConfigForm, user=Depends(get_admin_user)):
    values = form_data.model_dump(exclude_unset=True)
    updates = {QUOTA_CONFIG_KEYS[name]: value for name, value in values.items() if value is not None}
    await Config.upsert(updates)
    await publish_event(
        request,
        EVENTS.CONFIG_UPDATED,
        actor=user,
        subject_id='usage_quota',
        subject_type='config',
        data={'keys': list(updates)},
    )
    return await get_quota_settings()
