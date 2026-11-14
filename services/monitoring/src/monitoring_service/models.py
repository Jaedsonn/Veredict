from sqlalchemy.orm import DeclarativeBase

from veriditi_common.db import make_metadata


class Base(DeclarativeBase):
    """MetaData próprio do monitoring; as tabelas nascem no #5"""

    metadata = make_metadata()
