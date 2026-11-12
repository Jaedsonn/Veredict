"""Rotas de perfil do usuário autenticado (`/me`) ([S1-10], RF06)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status

from auth_service.dependencies import (
    CurrentUserDep,
    RequestContextDep,
    get_change_password_use_case,
    get_profile_use_case,
    get_update_profile_use_case,
)
from auth_service.schemas import PasswordChange, ProfileRead, ProfileUpdate
from auth_service.use_cases import (
    ChangePassword,
    ChangePasswordCommand,
    GetProfile,
    UpdateProfile,
    UpdateProfileCommand,
)

router = APIRouter(prefix="/me", tags=["profile"])


@router.get("", response_model=ProfileRead, status_code=status.HTTP_200_OK)
async def read_profile(
    current_user: CurrentUserDep,
    use_case: Annotated[GetProfile, Depends(get_profile_use_case)],
) -> ProfileRead:
    user = await use_case.execute(current_user.id)
    return ProfileRead.model_validate(user)


@router.patch("", response_model=ProfileRead, status_code=status.HTTP_200_OK)
async def update_profile(
    payload: ProfileUpdate,
    current_user: CurrentUserDep,
    ctx: RequestContextDep,
    use_case: Annotated[UpdateProfile, Depends(get_update_profile_use_case)],
) -> ProfileRead:
    user = await use_case.execute(
        UpdateProfileCommand(user_id=current_user.id, name=payload.name),
        ctx,
    )
    return ProfileRead.model_validate(user)


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def change_password(
    payload: PasswordChange,
    current_user: CurrentUserDep,
    ctx: RequestContextDep,
    use_case: Annotated[ChangePassword, Depends(get_change_password_use_case)],
    x_refresh_token: Annotated[str | None, Header(alias="X-Refresh-Token")] = None,
) -> Response:
    current_refresh = payload.refresh_token or x_refresh_token
    await use_case.execute(
        ChangePasswordCommand(
            user_id=current_user.id,
            current_password=payload.current_password,
            new_password=payload.new_password,
            current_session_id=current_user.session_id,
            current_refresh_token=current_refresh,
        ),
        ctx,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
