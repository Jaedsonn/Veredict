import { NextResponse, type NextRequest } from "next/server";

import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/tokens";

/**
 * Sessão inválida detectada durante o render (Server Components não podem
 * apagar cookies). Limpa os cookies e volta para /entrar com o aviso (#14).
 */
export function GET(request: NextRequest) {
  const url = new URL("/entrar", request.url);
  url.searchParams.set("expirado", "1");
  const res = NextResponse.redirect(url);
  res.cookies.delete(ACCESS_COOKIE);
  res.cookies.delete(REFRESH_COOKIE);
  return res;
}
