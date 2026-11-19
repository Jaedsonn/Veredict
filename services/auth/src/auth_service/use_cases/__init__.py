"""Casos de uso do serviço de Autenticação (camada de aplicação)"""

from auth_service.use_cases.authenticate_user import (
    AuthenticateUser,
    LoginCommand,
    LogoutCommand,
    LogoutUser,
    RefreshCommand,
    RefreshSession,
)
from auth_service.use_cases.password_reset import (
    RequestPasswordReset,
    RequestPasswordResetCommand,
    ResetPassword,
    ResetPasswordCommand,
)
from auth_service.use_cases.profile import (
    ChangePassword,
    ChangePasswordCommand,
    GetProfile,
    ProfileView,
    UpdateProfile,
    UpdateProfileCommand,
)
from auth_service.use_cases.register_user import RegisterCommand, RegisterUser
from auth_service.use_cases.verify_email import (
    ResendVerificationCode,
    ResendVerificationCommand,
    VerifyEmail,
    VerifyEmailCommand,
)

__all__ = [
    "AuthenticateUser",
    "ChangePassword",
    "ChangePasswordCommand",
    "GetProfile",
    "ProfileView",
    "LoginCommand",
    "LogoutCommand",
    "LogoutUser",
    "RefreshCommand",
    "RefreshSession",
    "RegisterCommand",
    "RegisterUser",
    "RequestPasswordReset",
    "RequestPasswordResetCommand",
    "ResendVerificationCode",
    "ResendVerificationCommand",
    "ResetPassword",
    "ResetPasswordCommand",
    "UpdateProfile",
    "UpdateProfileCommand",
    "VerifyEmail",
    "VerifyEmailCommand",
]
