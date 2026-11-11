import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { gatewayFetch } from "./gateway";

/** Contrato de `GET /api/me` (#10). */
export type Profile = {
  id: number;
  name: string;
  email: string;
  status: "pending_verification" | "active" | "blocked";
  email_verified_at: string | null;
  created_at: string;
};

/**
 * Data Access Layer do usuário logado. `cache` evita buscar o perfil duas vezes
 * no mesmo request (layout + página).
 */
export const getCurrentUser = cache(async (): Promise<Profile> => {
  const res = await gatewayFetch<Profile>("/api/me");
  if (res.ok) return res.data;
  if (res.error.status === 401) redirect("/sessao/expirada");
  throw new Error(res.error.message);
});
