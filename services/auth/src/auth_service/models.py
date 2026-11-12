from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from veriditi_common.db import make_metadata
from veriditi_common.db_types import BigIntPK, UTCDateTime, UtcNow


class Base(DeclarativeBase):
    """MetaData próprio do auth com a naming_convention do contrato"""

    metadata = make_metadata()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    # Sem index=True: geraria ix_users_email, e o contrato pede a constraint uq_users_email
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=UtcNow())
