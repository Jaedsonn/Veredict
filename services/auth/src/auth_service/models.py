"""Modelos ORM do serviço `auth` (`users`, `email_verification_codes`, `refresh_tokens`)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from veriditi_common.db import make_metadata
from veriditi_common.db_types import (
    BigIntPK,
    HashHex,
    UTCDateTime,
    UtcNow,
    UUIDStr,
    str_enum,
    utcnow,
)


class Base(DeclarativeBase):
    """Base exclusiva do `auth-service` -> MetaData isolado para o Alembic."""

    metadata = make_metadata()


class UserStatus(enum.StrEnum):
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    BLOCKED = "blocked"


class UserRole(enum.StrEnum):
    """Perfis de usuário da 1ª versão conforme Decisão D1 e Apêndice A (REQ 01)."""

    COMMON = "common"
    LAWYER = "lawyer"


class VerificationPurpose(enum.StrEnum):
    EMAIL_VERIFICATION = "email_verification"
    MFA = "mfa"


class RevokeReason(enum.StrEnum):
    ROTATED = "rotated"
    LOGOUT = "logout"
    REUSE_DETECTED = "reuse_detected"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status <> 'active' OR email_verified_at IS NOT NULL",
            name="active_requires_verified",
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        str_enum(UserStatus, "status"),
        default=UserStatus.PENDING_VERIFICATION,
        server_default=UserStatus.PENDING_VERIFICATION.value,
        nullable=False,
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utcnow,
        server_default=UtcNow(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utcnow,
        onupdate=utcnow,
        server_default=UtcNow(),
        nullable=False,
    )


class EmailVerificationCode(Base):
    __tablename__ = "email_verification_codes"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index(
            "ix_email_verification_codes_user_id_consumed_at",
            "user_id",
            "consumed_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    purpose: Mapped[VerificationPurpose] = mapped_column(
        str_enum(VerificationPurpose, "purpose"),
        default=VerificationPurpose.EMAIL_VERIFICATION,
        server_default=VerificationPurpose.EMAIL_VERIFICATION.value,
        nullable=False,
    )
    code_hash: Mapped[str] = mapped_column(HashHex(), nullable=False)
    attempts: Mapped[int] = mapped_column(
        SmallInteger().with_variant(mysql.TINYINT(), "mysql"),
        default=0,
        server_default="0",
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utcnow,
        server_default=UtcNow(),
        nullable=False,
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        CheckConstraint(
            "(revoked_at IS NULL) = (revoke_reason IS NULL)",
            name="revocation_consistent",
        ),
        Index("ix_refresh_tokens_user_id_revoked_at", "user_id", "revoked_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(HashHex(), unique=True, nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(UUIDStr(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    revoke_reason: Mapped[RevokeReason | None] = mapped_column(
        str_enum(RevokeReason, "revoke_reason"),
        nullable=True,
    )
    created_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utcnow,
        server_default=UtcNow(),
        nullable=False,
    )
