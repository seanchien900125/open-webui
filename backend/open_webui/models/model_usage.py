"""Token ledger: one row per finished model call, kept for quota enforcement.

``chat_message.usage`` cannot back a quota. It exists only for saved chats, so
temporary chats and API-key traffic would escape the limit. This table is written
for every call that reports usage, whatever its origin.
"""

import time
import uuid

from open_webui.internal.db import Base, get_async_db_context
from sqlalchemy import BigInteger, Column, Index, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class ModelUsage(Base):
    __tablename__ = 'model_usage'

    id = Column(Text, primary_key=True)
    user_id = Column(Text, nullable=False)
    model_id = Column(Text, nullable=True)
    input_tokens = Column(BigInteger, nullable=False, default=0)
    output_tokens = Column(BigInteger, nullable=False, default=0)
    total_tokens = Column(BigInteger, nullable=False, default=0)
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (Index('model_usage_user_created_idx', 'user_id', 'created_at'),)


class ModelUsageTable:
    async def record(
        self,
        user_id: str,
        model_id: str | None,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        db: AsyncSession | None = None,
    ) -> None:
        async with get_async_db_context(db) as session:
            session.add(
                ModelUsage(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    model_id=model_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    created_at=int(time.time()),
                )
            )
            await session.commit()

    async def sum_total_tokens(self, user_id: str, since: int, db: AsyncSession | None = None) -> int:
        """Tokens the user has used since ``since`` (epoch seconds, inclusive)."""
        async with get_async_db_context(db) as session:
            result = await session.execute(
                select(func.coalesce(func.sum(ModelUsage.total_tokens), 0)).where(
                    ModelUsage.user_id == user_id, ModelUsage.created_at >= since
                )
            )
            return int(result.scalar() or 0)


ModelUsages = ModelUsageTable()
