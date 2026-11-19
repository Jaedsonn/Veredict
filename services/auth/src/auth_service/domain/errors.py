"""Exceções de domínio do serviço de Autenticação"""


class DomainError(Exception):
    """Classe base para erros de regra de negócio do domínio de autenticação"""

    def __init__(self, code: str, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field


class AlreadyRegisteredError(DomainError):
    """Dado único já cadastrado (`409` com `code` por campo); a #61 troca por resposta uniforme"""


class EmailAlreadyRegisteredError(AlreadyRegisteredError):
    """E-mail já cadastrado na base (`409 Conflict`)"""

    def __init__(self, email: str) -> None:
        super().__init__(
            code="email_already_registered",
            message="Este e-mail já está cadastrado.",
            field="email",
        )
        self.email = email


class CpfAlreadyRegisteredError(AlreadyRegisteredError):
    """CPF já cadastrado (`409 Conflict`); nunca carrega o CPF"""

    def __init__(self) -> None:
        super().__init__(
            code="cpf_already_registered",
            message="Este CPF já está cadastrado.",
            field="cpf",
        )


class OabAlreadyRegisteredError(AlreadyRegisteredError):
    """Inscrição na OAB (UF e número) já cadastrada (`409 Conflict`)"""

    def __init__(self) -> None:
        super().__init__(
            code="oab_already_registered",
            message="Esta inscrição na OAB já está cadastrada.",
            field="oab",
        )


class InvalidFieldError(DomainError):
    """Campo recusado por regra de domínio (`422`, no formato de validação)"""

    def __init__(self, code: str, message: str, *, field: str) -> None:
        super().__init__(code=code, message=message, field=field)


class InvalidCpfError(InvalidFieldError):
    """CPF com formato ou dígitos verificadores inválidos; nunca carrega o valor"""

    def __init__(self) -> None:
        super().__init__(code="invalid_cpf", message="CPF inválido.", field="cpf")


class InvalidOabError(InvalidFieldError):
    """Inscrição na OAB inválida ou incoerente com o tipo de conta"""

    def __init__(self, message: str, *, field: str = "oab") -> None:
        super().__init__(code="invalid_oab", message=message, field=field)


class CpfDecryptionError(Exception):
    """Cifra adulterada, de outra chave, de versão desconhecida ou de outra linha; vira 500"""

    def __init__(self) -> None:
        super().__init__("Não foi possível decifrar o CPF")


class WeakPasswordError(DomainError):
    """Senha viola a política de segurança (`422 Unprocessable Entity`)"""

    def __init__(self, message: str, *, field: str = "password") -> None:
        super().__init__(code="weak_password", message=message, field=field)


class VerificationCodeExpiredError(DomainError):
    """Código de verificação expirado, inexistente ou já utilizado (`400 Bad Request`)"""

    def __init__(self) -> None:
        super().__init__(
            code="code_expired",
            message="Código expirado, solicite outro.",
            field="code",
        )


class VerificationCodeTooManyAttemptsError(DomainError):
    """Código bloqueado após atingir o limite de 5 tentativas (`400 Bad Request`)"""

    def __init__(self) -> None:
        super().__init__(
            code="too_many_attempts",
            message="Muitas tentativas com este código. Solicite um novo código.",
            field="code",
        )


class InvalidVerificationCodeError(DomainError):
    """Código informado não confere (`400 Bad Request`)"""

    def __init__(self, attempts_remaining: int) -> None:
        super().__init__(
            code="invalid_code",
            message="Código incorreto.",
            field="code",
        )
        self.attempts_remaining = attempts_remaining


class InvalidCredentialsError(DomainError):
    """E-mail ou senha inválidos no login (`401 Unauthorized`)"""

    def __init__(self) -> None:
        super().__init__(
            code="invalid_credentials",
            message="E-mail ou senha incorretos.",
        )


class EmailNotVerifiedError(DomainError):
    """Tentativa de login em conta ainda pendente de verificação (`403 Forbidden`)"""

    def __init__(self) -> None:
        super().__init__(
            code="email_not_verified",
            message="Confirme seu e-mail antes de entrar.",
        )


class AccountBlockedError(DomainError):
    """Tentativa de uso de conta bloqueada (`403 Forbidden`)"""

    def __init__(self) -> None:
        super().__init__(
            code="account_blocked",
            message="Esta conta está bloqueada.",
        )


class InvalidRefreshTokenError(DomainError):
    """Refresh token inexistente ou expirado (`401 Unauthorized`)"""

    def __init__(self) -> None:
        super().__init__(
            code="invalid_refresh",
            message="Sessão inválida ou expirada.",
        )


class RefreshTokenReuseDetectedError(DomainError):
    """Reuso de refresh token já revogado detectado (`401 Unauthorized`)"""

    def __init__(self) -> None:
        super().__init__(
            code="refresh_reuse_detected",
            message="Sessão revogada por segurança.",
        )


class UserNotFoundError(DomainError):
    """Usuário não encontrado (`404 Not Found`)"""

    def __init__(self) -> None:
        super().__init__(
            code="user_not_found",
            message="Usuário não encontrado.",
        )


class InvalidCurrentPasswordError(DomainError):
    """Senha atual incorreta na troca de senha (`400 Bad Request`)"""

    def __init__(self) -> None:
        super().__init__(
            code="invalid_current_password",
            message="A senha atual está incorreta.",
            field="current_password",
        )


class InvalidResetTokenError(DomainError):
    """Link de redefinição malformado, inexistente, expirado, usado ou substituído (`400`)"""

    def __init__(self) -> None:
        super().__init__(
            code="invalid_reset_token",
            message="Link inválido ou expirado. Solicite um novo.",
            field="token",
        )
