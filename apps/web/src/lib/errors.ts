/**
 * Tradução das respostas de erro do gateway para mensagens em PT-BR (RNF07).
 *
 * Formatos aceitos (FastAPI):
 *   { "detail": "texto" }
 *   { "detail": [{ "loc": ["body", "password"], "msg": "..." }] }     (422)
 *   { "detail": { "code": "email_not_verified", "message": "...", ... } }
 *   { "code": "email_not_verified", "detail": "..." }
 */

export type ApiError = {
  status: number;
  code?: string;
  message: string;
  fieldErrors: Record<string, string>;
  /** Segundos do header Retry-After (429). */
  retryAfter?: number;
  /** Dados extras do erro (ex.: attempts_remaining). */
  extra: Record<string, unknown>;
};

const CODE_MESSAGES: Record<string, string> = {
  email_not_verified: "Confirme seu e-mail antes de entrar.",
  invalid_credentials: "E-mail ou senha incorretos.",
  email_already_registered: "Este e-mail já está cadastrado.",
  invalid_code: "Código incorreto.",
  code_expired: "Código expirado, solicite outro.",
  code_consumed: "Código expirado, solicite outro.",
  too_many_attempts: "Muitas tentativas com este código. Solicite um novo código.",
  invalid_current_password: "A senha atual está incorreta.",
  gateway_unavailable: "Serviço indisponível no momento. Tente novamente em instantes.",
};

const STATUS_MESSAGES: Record<number, string> = {
  400: "Não foi possível concluir a operação.",
  401: "Sua sessão expirou. Entre novamente.",
  403: "Você não tem permissão para esta ação.",
  404: "Recurso não encontrado.",
  409: "Este e-mail já está cadastrado.",
  422: "Verifique os campos destacados.",
  429: "Muitas tentativas. Aguarde um pouco e tente novamente.",
  503: "Serviço indisponível no momento. Tente novamente em instantes.",
  504: "O serviço demorou para responder. Tente novamente.",
};

export function messageForCode(code: string | undefined, status: number): string {
  if (code && CODE_MESSAGES[code]) return CODE_MESSAGES[code];
  return STATUS_MESSAGES[status] ?? "Algo deu errado. Tente novamente.";
}

type ValidationItem = { loc?: unknown[]; msg?: string };

export function parseApiError(status: number, body: unknown, retryAfterHeader?: string | null): ApiError {
  const root = (body ?? {}) as Record<string, unknown>;
  const detail = root.detail;
  const fieldErrors: Record<string, string> = {};
  let code = typeof root.code === "string" ? root.code : undefined;
  let serverMessage: string | undefined;
  let extra: Record<string, unknown> = {};

  if (typeof detail === "string") {
    serverMessage = detail;
  } else if (Array.isArray(detail)) {
    for (const item of detail as ValidationItem[]) {
      const field = item.loc?.filter((p) => p !== "body").join(".");
      if (field && item.msg && !fieldErrors[field]) fieldErrors[field] = item.msg;
    }
  } else if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    if (typeof d.code === "string") code = d.code;
    if (typeof d.message === "string") serverMessage = d.message;
    extra = d;
  }

  const retryAfter = retryAfterHeader ? Number.parseInt(retryAfterHeader, 10) : undefined;

  // Mensagens conhecidas têm prioridade: o backend pode responder em inglês.
  const message =
    code && CODE_MESSAGES[code]
      ? CODE_MESSAGES[code]
      : (serverMessage ?? messageForCode(code, status));

  return {
    status,
    code,
    message,
    fieldErrors,
    retryAfter: Number.isFinite(retryAfter) ? retryAfter : undefined,
    extra,
  };
}

export function unavailableError(): ApiError {
  return {
    status: 503,
    code: "gateway_unavailable",
    message: messageForCode("gateway_unavailable", 503),
    fieldErrors: {},
    extra: {},
  };
}
