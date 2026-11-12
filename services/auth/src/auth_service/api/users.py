from fastapi import APIRouter, HTTPException, Query, status

from auth_service.dependencies import UserRepoDep
from auth_service.repository import EmailAlreadyExistsError
from auth_service.schemas import UserCreate, UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
async def list_users(
    repo: UserRepoDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await repo.list(limit=limit, offset=offset)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: int, repo: UserRepoDep):
    user = await repo.get(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, repo: UserRepoDep):
    try:
        return await repo.create(payload)
    except EmailAlreadyExistsError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
