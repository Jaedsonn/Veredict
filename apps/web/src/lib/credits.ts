import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { gatewayFetch } from "./gateway";

/** Pacote da D2 com os campos do Apêndice A (`GET /api/packages`, #21). */
export type CreditPackage = {
  code: string;
  name: string;
  credits: number;
  unit_price_cents: number;
  price_cents: number;
  currency: string;
  benefits: string;
  highlight: boolean;
};

export type OrderStatus = "pending" | "paid" | "expired" | "failed";

/** Contrato de `GET /api/orders/{id}` (#22). */
export type Order = {
  id: string;
  status: OrderStatus;
  package: { code: string; name: string };
  credits: number;
  amount_cents: number;
  currency: string;
  provider: string;
  pix_copy_paste: string | null;
  pix_qr_svg: string | null;
  billing: {
    name: string;
    email: string;
    phone: string;
    cpf_masked: string;
    cep: string;
    street: string;
    number: string;
    complement: string | null;
    district: string;
    city: string;
    state: string;
  };
  expires_at: string;
  paid_at: string | null;
  created_at: string;
};

export type LedgerEntry = {
  id: number;
  delta: number;
  reason: "purchase" | "capture" | "refund" | "adjustment";
  reference_id: string;
  balance_after: number;
  created_at: string;
};

export type Statement = { balance: number; entries: LedgerEntry[] };

/** Catálogo público; `cache` evita buscar duas vezes no mesmo request. */
export const getPackages = cache(async (): Promise<CreditPackage[]> => {
  const res = await gatewayFetch<CreditPackage[]>("/api/packages", { auth: false });
  if (res.ok) return res.data;
  throw new Error(res.error.message);
});

/** Saldo atual, ou `null` se o pagamento estiver fora do ar (o painel segue de pé, RNF02). */
export const getBalance = cache(async (): Promise<number | null> => {
  const res = await gatewayFetch<{ balance: number }>("/api/credits/balance");
  if (res.ok) return res.data.balance;
  if (res.error.status === 401) redirect("/sessao/expirada");
  return null;
});

export async function getStatement(): Promise<Statement> {
  const res = await gatewayFetch<Statement>("/api/credits/statement");
  if (res.ok) return res.data;
  if (res.error.status === 401) redirect("/sessao/expirada");
  throw new Error(res.error.message);
}

/** `null` quando o pedido não existe ou é de outra pessoa (o serviço responde 404). */
export async function getOrder(id: string): Promise<Order | null> {
  if (!/^[0-9a-f-]{36}$/i.test(id)) return null;
  const res = await gatewayFetch<Order>(`/api/orders/${id}`);
  if (res.ok) return res.data;
  if (res.error.status === 401) redirect("/sessao/expirada");
  if (res.error.status === 404) return null;
  throw new Error(res.error.message);
}
