import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { gatewayFetch } from "./gateway";
import type { OabKind, OabUf } from "./validation/oab";

/** Inscrição como o advogado informou no cadastro; ainda sem consulta ao CNA (#64). */
export type ProfileOab = { number: string; uf: OabUf; kind: OabKind };

/** Contrato de `GET /api/me` (#10; tipo, CPF mascarado e OAB na #60). */
export type Profile = {
  id: number;
  name: string;
  email: string;
  status: "pending_verification" | "active" | "blocked";
  email_verified_at: string | null;
  created_at: string;
  user_type: "common" | "lawyer";
  /** Só o meio do CPF (`***.982.247-**`): o número inteiro não sai do auth. */
  cpf_masked: string;
  oab: ProfileOab | null;
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
