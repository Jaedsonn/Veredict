from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Contrato de ENTRADA: o que o cliente pode enviar."""

    email: EmailStr
    name: str = Field(min_length=1, max_length=120)


class UserRead(BaseModel):
    """Contrato de SAÍDA: o que a API expõe (nunca o model ORM diretamente)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str
    created_at: datetime
