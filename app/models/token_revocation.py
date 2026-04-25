"""Token revocation model for server-side logout."""
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from datetime import datetime
import uuid

from app.models.base import Base


class TokenRevocation(Base):
    """Server-side token revocation for logout and security."""
    __tablename__ = "token_revocations"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    token_jti = Column(String(255), unique=True, nullable=False, index=True)
    revoked_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
