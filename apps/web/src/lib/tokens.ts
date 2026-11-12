/**
 * Tipos e regras dos tokens emitidos pelo serviço de autenticação (#9).
 * Sem `server-only` porque também é usado pelo proxy.ts.
 */

export const ACCESS_COOKIE = "vrd_access";
export const REFRESH_COOKIE = "vrd_refresh";

/** Duração do refresh token definida em #9 (7 dias). */
export const REFRESH_MAX_AGE_S = 7 * 24 * 60 * 60;

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  /** Validade do access token em segundos (15 min no #9). */
  expires_in: number;
};

export type CookieSpec = {
  name: string;
  value: string;
  options: {
    httpOnly: true;
    secure: boolean;
    sameSite: "lax";
    path: "/";
    maxAge: number;
  };
};

/**
 * Cookies httpOnly (o JavaScript do navegador nunca lê o JWT — ADR-017).
 * O cookie do access token expira junto com o token: cookie ausente + refresh
 * presente significa "renovar a sessão".
 */
export function sessionCookies(tokens: TokenPair): CookieSpec[] {
  const base = {
    httpOnly: true as const,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/" as const,
  };
  return [
    {
      name: ACCESS_COOKIE,
      value: tokens.access_token,
      // Margem de 10 s para não enviar um token que expira no meio do caminho.
      options: { ...base, maxAge: Math.max(tokens.expires_in - 10, 1) },
    },
    {
      name: REFRESH_COOKIE,
      value: tokens.refresh_token,
      options: { ...base, maxAge: REFRESH_MAX_AGE_S },
    },
  ];
}

function isTokenPair(value: unknown): value is TokenPair {
  const v = value as Partial<TokenPair> | null;
  return (
    typeof v?.access_token === "string" &&
    typeof v.refresh_token === "string" &&
    typeof v.expires_in === "number"
  );
}

/*
 * Deduplicação de refresh.
 * O refresh token é rotacionado a cada uso e o reuso de um token já revogado
 * derruba todas as sessões do usuário (#9). Requisições paralelas (prefetch de
 * links, várias abas) chegariam com o MESMO refresh token: só a primeira chama o
 * gateway; as demais reaproveitam o resultado por alguns segundos.
 */
const REFRESH_GRACE_MS = 30_000;
const inflight = new Map<string, { promise: Promise<TokenPair | null>; at: number }>();

export function refreshTokens(
  gatewayUrl: string,
  refreshToken: string,
  headers: Record<string, string> = {},
): Promise<TokenPair | null> {
  const now = Date.now();
  for (const [key, entry] of inflight) {
    if (now - entry.at > REFRESH_GRACE_MS) inflight.delete(key);
  }
  const cached = inflight.get(refreshToken);
  if (cached) return cached.promise;

  const promise = (async () => {
    try {
      const res = await fetch(new URL("/api/auth/refresh", gatewayUrl), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ refresh_token: refreshToken }),
        signal: AbortSignal.timeout(5_000),
        cache: "no-store",
      });
      if (!res.ok) return null;
      const data: unknown = await res.json();
      return isTokenPair(data) ? data : null;
    } catch {
      return null;
    }
  })();

  inflight.set(refreshToken, { promise, at: now });
  return promise;
}
