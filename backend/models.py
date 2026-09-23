"""
backend/models.py — SQLAlchemy ORM Models for Better Auth Schema
================================================================
Defines User and Session models matching the existing PostgreSQL tables
created and managed by Next.js Drizzle ORM / Better Auth.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    """
    Represents an authenticated user in the 'user' table managed by Better Auth.
    """
    __tablename__ = "user"

    id = Column(Text, primary_key=True, index=True)
    name = Column(Text, nullable=False)
    email = Column(Text, nullable=False, unique=True, index=True)
    email_verified = Column(Boolean, nullable=False, default=False)
    image = Column(Text, nullable=True)
    role = Column(Text, nullable=True, default="user")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sessions = relationship(
        "Session",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def to_dict(self) -> dict:
        """Serializes user model to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "email_verified": self.email_verified,
            "image": self.image,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<User(id={self.id!r}, email={self.email!r}, role={self.role!r})>"


class Session(Base):
    """
    Represents an active session in the 'session' table managed by Better Auth.
    Better Auth stores session tokens here with expiration timestamps.
    """
    __tablename__ = "session"

    id = Column(Text, primary_key=True, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    token = Column(Text, nullable=False, unique=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    ip_address = Column(Text, nullable=True)
    user_agent = Column(Text, nullable=True)
    user_id = Column(Text, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)

    # Relationships
    user = relationship(
        "User",
        back_populates="sessions",
        lazy="joined",
    )

    def is_expired(self, current_time: Optional[datetime] = None) -> bool:
        """Checks whether the session has expired relative to UTC time."""
        from datetime import timezone
        now = current_time or datetime.now(timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now >= expires

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "token": self.token,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
        }

    def __repr__(self) -> str:
        return f"<Session(id={self.id!r}, user_id={self.user_id!r}, expires_at={self.expires_at!r})>"
