from sqlalchemy.orm import DeclarativeBase

from veriditi_common.db import make_metadata


class Base(DeclarativeBase):
    """MetaData próprio do notification; as tabelas nascem no #6"""

    metadata = make_metadata()
