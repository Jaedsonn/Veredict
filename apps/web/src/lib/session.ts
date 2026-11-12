import "server-only";

import { cookies } from "next/headers";

import { ACCESS_COOKIE, REFRESH_COOKIE, sessionCookies, type TokenPair } from "./tokens";

/** Só funciona em Server Actions e Route Handlers (regra do Next para escrita de cookies). */
export async function setSession(tokens: TokenPair): Promise<void> {
  const store = await cookies();
  for (const c of sessionCookies(tokens)) store.set(c.name, c.value, c.options);
}

export async function clearSession(): Promise<void> {
  const store = await cookies();
  store.delete(ACCESS_COOKIE);
  store.delete(REFRESH_COOKIE);
}

export async function getAccessToken(): Promise<string | undefined> {
  return (await cookies()).get(ACCESS_COOKIE)?.value;
}

export async function getRefreshToken(): Promise<string | undefined> {
  return (await cookies()).get(REFRESH_COOKIE)?.value;
}
