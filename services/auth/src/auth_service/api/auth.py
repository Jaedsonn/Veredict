"""Rotas de registro, verificação de e-mail e sessão (`/auth/*`) ([S1-07], [S1-08], [S1-09])"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from auth_service.dependencies import (
    RequestContextDep,
    get_authenticate_user_use_case,
    get_logout_user_use_case,
    get_refresh_session_use_case,
    get_register_user_use_case,
    get_resend_code_use_case,
    get_verify_email_use_case,
)
from auth_service.domain.entities import AuthenticatedResult
from auth_service.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResendVerificationResponse,
    TokenPairResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from auth_service.use_cases import (
    AuthenticateUser,
    LoginCommand,
    LogoutCommand,
    LogoutUser,
    RefreshCommand,
    RefreshSession,
    RegisterCommand,
    RegisterUser,
    ResendVerificationCode,
    ResendVerificationCommand,
    VerifyEmail,
    VerifyEmailCommand,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    ctx: RequestContextDep,
    use_case: Annotated[RegisterUser, Depends(get_register_user_use_case)],
) -> RegisterResponse:
    user = await use_case.execute(
        RegisterCommand(
            name=payload.name,
            email=payload.email,
            password=payload.password,
        ),
        ctx,
    )
    return RegisterResponse(id=user.id, email=user.email, status=user.status)


@router.post(
    "/verify-email",
    response_model=VerifyEmailResponse,
    status_code=status.HTTP_200_OK,
)
async def verify_email(
    payload: VerifyEmailRequest,
    ctx: RequestContextDep,
    use_case: Annotated[VerifyEmail, Depends(get_verify_email_use_case)],
) -> VerifyEmailResponse:
    user = await use_case.execute(
        VerifyEmailCommand(email=payload.email, code=payload.code),
        ctx,
    )
    return VerifyEmailResponse(status=user.status)


@router.post(
    "/verify-email/resend",
    response_model=ResendVerificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resend_verification_email(
    payload: ResendVerificationRequest,
    ctx: RequestContextDep,
    use_case: Annotated[ResendVerificationCode, Depends(get_resend_code_use_case)],
) -> ResendVerificationResponse:
    await use_case.execute(ResendVerificationCommand(email=payload.email), ctx)
    return ResendVerificationResponse(status="accepted")


@router.post(
    "/login",
    response_model=TokenPairResponse,
    status_code=status.HTTP_200_OK,
)
async def login(
    payload: LoginRequest,
    ctx: RequestContextDep,
    use_case: Annotated[AuthenticateUser, Depends(get_authenticate_user_use_case)],
) -> TokenPairResponse:
    result = await use_case.execute(
        LoginCommand(email=payload.email, password=payload.password),
        ctx,
    )
    assert isinstance(result, AuthenticatedResult)
    return TokenPairResponse(
        access_token=result.tokens.access_token,
        refresh_token=result.tokens.refresh_token,
        expires_in=result.tokens.expires_in,
    )


@router.post(
    "/refresh",
    response_model=TokenPairResponse,
    status_code=status.HTTP_200_OK,
)
async def refresh_session(
    payload: RefreshRequest,
    ctx: RequestContextDep,
    use_case: Annotated[RefreshSession, Depends(get_refresh_session_use_case)],
) -> TokenPairResponse:
    tokens = await use_case.execute(
        RefreshCommand(refresh_token=payload.refresh_token),
        ctx,
    )
    return TokenPairResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def logout(
    payload: LogoutRequest,
    ctx: RequestContextDep,
    use_case: Annotated[LogoutUser, Depends(get_logout_user_use_case)],
) -> Response:
    await use_case.execute(
        LogoutCommand(refresh_token=payload.refresh_token),
        ctx,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
