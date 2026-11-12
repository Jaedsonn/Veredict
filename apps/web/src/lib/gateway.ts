import "server-only";

import { cookies, headers } from "next/headers";

import { GATEWAY_TIMEOUT_MS, GATEWAY_URL } from "./config";
import { parseApiError, unavailableError, type ApiError } from "./errors";
import { ACCESS_COOKIE, REFRESH_COOKIE, refreshTokens, sessionCookies } from "./tokens";

export type ApiResult<T> = { ok: true; status: number; data: T } | { ok: false; error: ApiError };

type GatewayInit = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  /** Envia `Authorization: Bearer` a partir do cookie (padrão: true). */
  auth?: boolean;
};

/** Repassa o IP real do usuário: a auditoria precisa dele (ADR-001 / #11). */
async function forwardedHeaders(): Promise<Record<string, string>> {
  const h = await headers();
  const out: Record<string, string> = {};
  const xff = h.get("x-forwarded-for");
  const realIp = h.get("x-real-ip");
  if (xff) out["X-Forwarded-For"] = xff;
  else if (realIp) out["X-Forwarded-For"] = realIp;
  const ua = h.get("user-agent");
  if (ua) out["User-Agent"] = ua;
  return out;
}

async function send(path: string, init: GatewayInit, token: string | undefined, extra: Record<string, string>) {
  const reqHeaders: Record<string, string> = { Accept: "application/json", ...extra };
  if (init.body !== undefined) reqHeaders["Content-Type"] = "application/json";
  if (token) reqHeaders.Authorization = `Bearer ${token}`;

  return fetch(new URL(path, GATEWAY_URL), {
    method: init.method ?? "GET",
    headers: reqHeaders,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    signal: AbortSignal.timeout(GATEWAY_TIMEOUT_MS),
    cache: "no-store",
  });
}

/**
 * Cliente do API Gateway — só roda no servidor (BFF, ADR-017).
 * Em 401 numa rota autenticada, tenta renovar a sessão UMA vez e repete a chamada.
 */
export async function gatewayFetch<T = unknown>(path: string, init: GatewayInit = {}): Promise<ApiResult<T>> {
  const useAuth = init.auth ?? true;
  const store = await cookies();
  const extra = await forwardedHeaders();

  try {
    let token = useAuth ? store.get(ACCESS_COOKIE)?.value : undefined;
    const refresh = useAuth ? store.get(REFRESH_COOKIE)?.value : undefined;

    let res: Response | undefined;
    if (!useAuth || token) res = await send(path, init, token, extra);

    if (useAuth && (!res || res.status === 401) && refresh) {
      const tokens = await refreshTokens(GATEWAY_URL, refresh, extra);
      if (tokens) {
        try {
          for (const c of sessionCookies(tokens)) store.set(c.name, c.value, c.options);
        } catch {
          // Server Component: cookies não podem ser escritos durante o render.
          // O proxy.ts renova a sessão antes de chegar aqui na navegação normal.
        }
        token = tokens.access_token;
        res = await send(path, init, token, extra);
      }
    }

    if (!res) {
      return { ok: false, error: parseApiError(401, null) };
    }

    const text = await res.text();
    const body: unknown = text ? safeJson(text) : null;

    if (!res.ok) {
      return { ok: false, error: parseApiError(res.status, body, res.headers.get("retry-after")) };
    }
    return { ok: true, status: res.status, data: body as T };
  } catch {
    // Timeout ou gateway fora do ar: a web continua de pé e mostra uma mensagem (RNF02).
    return { ok: false, error: unavailableError() };
  }
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}
