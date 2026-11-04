from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from users_service.repository import UserRepository


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    # O objeto Database vive em app.state (criado no lifespan) -> testes podem trocá-lo.
    async for session in request.app.state.db.session():
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_user_repository(session: SessionDep) -> UserRepository:
    return UserRepository(session)


UserRepoDep = Annotated[UserRepository, Depends(get_user_repository)]
