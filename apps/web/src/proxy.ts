import { NextResponse, type NextRequest } from "next/server";

import { ACCESS_COOKIE, REFRESH_COOKIE, refreshTokens, sessionCookies } from "@/lib/tokens";

const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://localhost:8080";

/** Rotas do grupo (app): exigem sessão. */
const PROTECTED = ["/painel", "/perfil"];
/** Telas de entrada: quem já está logado vai direto ao painel. */
const GUEST_ONLY = ["/entrar", "/cadastro"];

function matches(pathname: string, prefixes: string[]) {
  return prefixes.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/**
 * Checagem otimista de sessão (Next 16: `proxy.ts`, antigo `middleware.ts`).
 * A autorização de verdade acontece no gateway, que valida o JWT em toda chamada.
 */
export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const access = request.cookies.get(ACCESS_COOKIE)?.value;
  const refresh = request.cookies.get(REFRESH_COOKIE)?.value;

  if (matches(pathname, GUEST_ONLY)) {
    if (access || refresh) return NextResponse.redirect(new URL("/painel", request.url));
    return NextResponse.next();
  }

  if (!matches(pathname, PROTECTED)) return NextResponse.next();

  if (access) return NextResponse.next();

  const loginUrl = new URL("/entrar", request.url);
  loginUrl.searchParams.set("next", `${pathname}${search}`);

  if (!refresh) return NextResponse.redirect(loginUrl);

  // Access token expirado (o cookie expira junto): renova antes de renderizar,
  // porque Server Components não conseguem gravar cookies.
  const forwarded: Record<string, string> = {};
  const xff = request.headers.get("x-forwarded-for");
  if (xff) forwarded["X-Forwarded-For"] = xff;
  const ua = request.headers.get("user-agent");
  if (ua) forwarded["User-Agent"] = ua;

  const tokens = await refreshTokens(GATEWAY_URL, refresh, forwarded);
  if (!tokens) {
    loginUrl.searchParams.set("expirado", "1");
    const res = NextResponse.redirect(loginUrl);
    res.cookies.delete(ACCESS_COOKIE);
    res.cookies.delete(REFRESH_COOKIE);
    return res;
  }

  const cookies = sessionCookies(tokens);
  // Os novos cookies valem já nesta requisição (para o render) e na resposta (para o navegador).
  for (const c of cookies) request.cookies.set(c.name, c.value);
  const res = NextResponse.next({ request: { headers: request.headers } });
  for (const c of cookies) res.cookies.set(c.name, c.value, c.options);
  return res;
}

export const config = {
  matcher: ["/painel/:path*", "/perfil/:path*", "/entrar", "/cadastro"],
};
