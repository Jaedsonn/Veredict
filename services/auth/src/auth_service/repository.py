from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.models import User
from auth_service.schemas import UserCreate


class EmailAlreadyExistsError(Exception):
    pass


class UserRepository:
    """Única camada que conhece SQL/ORM. As rotas falam com o repositório,
    não com a sessão — trocar o banco ou testar fica isolado aqui."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def list(self, *, limit: int = 50, offset: int = 0) -> list[User]:
        stmt = select(User).order_by(User.id).limit(limit).offset(offset)
        return list((await self.session.scalars(stmt)).all())

    async def create(self, data: UserCreate) -> User:
        user = User(email=data.email, name=data.name)
        self.session.add(user)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            # A constraint UNIQUE do banco é a fonte da verdade; checar antes
            # com SELECT teria condição de corrida entre requisições concorrentes.
            await self.session.rollback()
            raise EmailAlreadyExistsError(data.email) from exc
        await self.session.refresh(user)
        return user
