from fastapi import APIRouter, Depends, Query, Request
from open_webui.events import EVENTS, publish_event
from open_webui.models.config import Config
from open_webui.utils.auth import get_admin_user
from open_webui.utils.retention import RETENTION_CONFIG_KEYS, count_expired, get_retention_settings
from pydantic import BaseModel, Field

router = APIRouter()


class ChatRetentionForm(BaseModel):
    ENABLE_CHAT_RETENTION: bool | None = None
    CHAT_RETENTION_DAYS: int | None = Field(default=None, ge=0)
    CHAT_RETENTION_KEEP_PINNED: bool | None = None
    CHAT_RETENTION_KEEP_ARCHIVED: bool | None = None


@router.get('/chats/config', response_model=ChatRetentionForm)
async def get_chat_retention_config(user=Depends(get_admin_user)):
    return await get_retention_settings()


@router.post('/chats/config', response_model=ChatRetentionForm)
async def set_chat_retention_config(request: Request, form_data: ChatRetentionForm, user=Depends(get_admin_user)):
    values = form_data.model_dump(exclude_unset=True)
    updates = {RETENTION_CONFIG_KEYS[name]: value for name, value in values.items() if value is not None}
    await Config.upsert(updates)
    await publish_event(
        request,
        EVENTS.CONFIG_UPDATED,
        actor=user,
        subject_id='chat_retention',
        subject_type='config',
        data={'keys': list(updates)},
    )
    return await get_retention_settings()


@router.get('/chats/preview')
async def preview_chat_retention(
    days: int = Query(ge=0),
    keep_pinned: bool = True,
    keep_archived: bool = False,
    user=Depends(get_admin_user),
):
    """How many chats would be deleted right now with these global settings. Deletes nothing.

    Group rules (including legal holds) are applied, so the number matches what a real pass would do.
    """
    settings = {
        'CHAT_RETENTION_DAYS': days,
        'CHAT_RETENTION_KEEP_PINNED': keep_pinned,
        'CHAT_RETENTION_KEEP_ARCHIVED': keep_archived,
    }
    return {'count': await count_expired(settings)}
