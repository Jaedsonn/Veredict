"use server";

import { redirect } from "next/navigation";

import { gatewayFetch } from "@/lib/gateway";
import { clearSession, getRefreshToken } from "@/lib/session";

export async function logoutAction(): Promise<void> {
  const refresh = await getRefreshToken();
  if (refresh) {
    // Revoga o refresh token no auth (#9). Mesmo se o gateway falhar,
    // os cookies são apagados: o usuário sai de qualquer forma.
    await gatewayFetch("/api/auth/logout", { method: "POST", body: { refresh_token: refresh } });
  }
  await clearSession();
  redirect("/entrar");
}
