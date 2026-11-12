from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """O Database vive em app.state (criado no lifespan) para os testes poderem trocá-lo"""
    async for session in request.app.state.db.session():
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
