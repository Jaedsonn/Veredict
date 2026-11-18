"""Rotas de registro, verificação de e-mail, sessão e recuperação de senha (`/auth/*`)"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from auth_service.dependencies import (
    RequestContextDep,
    get_authenticate_user_use_case,
    get_logout_user_use_case,
    get_refresh_session_use_case,
    get_register_user_use_case,
    get_request_password_reset_use_case,
    get_resend_code_use_case,
    get_reset_password_use_case,
    get_verify_email_use_case,
)
from auth_service.domain.cpf import Cpf
from auth_service.domain.entities import AuthenticatedResult
from auth_service.domain.oab import Oab
from auth_service.schemas import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResendVerificationResponse,
    ResetPasswordRequest,
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
    RequestPasswordReset,
    RequestPasswordResetCommand,
    ResendVerificationCode,
    ResendVerificationCommand,
    ResetPassword,
    ResetPasswordCommand,
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
            user_type=payload.user_type,
            cpf=Cpf(payload.cpf),
            oab=(
                Oab(number=payload.oab.number, uf=payload.oab.uf, kind=payload.oab.kind)
                if payload.oab
                else None
            ),
        ),
        ctx,
    )
    return RegisterResponse(
        id=user.id, email=user.email, status=user.status, user_type=user.user_type
    )


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


@router.post(
    "/password/forgot",
    response_model=ForgotPasswordResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    ctx: RequestContextDep,
    use_case: Annotated[RequestPasswordReset, Depends(get_request_password_reset_use_case)],
) -> ForgotPasswordResponse:
    await use_case.execute(RequestPasswordResetCommand(email=payload.email), ctx)
    return ForgotPasswordResponse(status="accepted")


@router.post(
    "/password/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def reset_password(
    payload: ResetPasswordRequest,
    ctx: RequestContextDep,
    use_case: Annotated[ResetPassword, Depends(get_reset_password_use_case)],
) -> Response:
    await use_case.execute(
        ResetPasswordCommand(token=payload.token, new_password=payload.new_password),
        ctx,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
