"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import type { Order } from "@/lib/credits";
import { publicValues, type FormState } from "@/lib/form-state";
import { gatewayFetch } from "@/lib/gateway";
import { billingSchema } from "@/lib/validation/billing";
import { fieldErrorsOf, formValues } from "@/lib/validation/auth";

const KEY_RE = /^[A-Za-z0-9._:-]{8,80}$/;

function newKey(): string {
  return crypto.randomUUID();
}

/**
 * Passos 2 e 3 do REQ05: valida o faturamento, cria o pedido e leva ao PIX.
 * A `Idempotency-Key` nasce com o formulário: um clique duplo devolve o mesmo pedido (#22).
 */
export async function createOrderAction(_prev: FormState, form: FormData): Promise<FormState> {
  const values = formValues(form);
  const packageCode = values.packageCode ?? "";
  const key = values.idempotencyKey ?? "";
  const parsed = billingSchema.safeParse(values);
  if (!parsed.success || !KEY_RE.test(key) || !/^[a-z0-9_-]{1,20}$/.test(packageCode)) {
    return {
      status: "error",
      fieldErrors: parsed.success ? undefined : fieldErrorsOf(parsed.error),
      message: parsed.success ? "Não foi possível criar o pedido. Recarregue a página." : undefined,
      values: publicValues(values),
    };
  }

  const res = await gatewayFetch<Order>("/api/orders", {
    method: "POST",
    body: { package_code: packageCode, billing: parsed.data },
    headers: { "Idempotency-Key": key },
  });

  if (!res.ok) {
    if (res.error.status === 401) redirect("/sessao/expirada");
    const fieldErrors: Record<string, string> = {};
    for (const [field, msg] of Object.entries(res.error.fieldErrors)) {
      if (field.startsWith("billing.")) fieldErrors[field.slice("billing.".length)] = msg;
    }
    return {
      status: "error",
      message: Object.keys(fieldErrors).length ? undefined : res.error.message,
      fieldErrors,
      values: publicValues(values),
      // Provedor fora do ar: o pedido ficou failed com esta chave, a próxima tentativa usa outra
      meta: { idempotencyKey: newKey() },
    };
  }

  if (res.data.status === "failed") {
    return {
      status: "error",
      message: "O pagamento não pôde ser iniciado. Tente novamente em instantes.",
      values: publicValues(values),
      meta: { idempotencyKey: newKey() },
    };
  }

  redirect(`/creditos/pedidos/${res.data.id}`);
}

export type OrderPoll = { ok: true; order: Order } | { ok: false; message: string };

/** Polling do status do PIX na tela do pedido. */
export async function pollOrderAction(orderId: string): Promise<OrderPoll> {
  if (!/^[0-9a-f-]{36}$/i.test(orderId)) return { ok: false, message: "Pedido não encontrado." };
  const res = await gatewayFetch<Order>(`/api/orders/${orderId}`);
  if (res.ok) return { ok: true, order: res.data };
  if (res.error.status === 401) redirect("/sessao/expirada");
  return { ok: false, message: res.error.message };
}

export type PaymentResult =
  | { ok: true; order: Order; balance: number }
  | { ok: false; message: string };

/** Sandbox (#22): faz o papel do banco confirmando o PIX. */
export async function simulatePaymentAction(orderId: string): Promise<PaymentResult> {
  if (!/^[0-9a-f-]{36}$/i.test(orderId)) return { ok: false, message: "Pedido não encontrado." };
  const res = await gatewayFetch<{ order: Order; balance: number }>(
    `/api/orders/${orderId}/simulate-payment`,
    { method: "POST" },
  );
  if (!res.ok) {
    if (res.error.status === 401) redirect("/sessao/expirada");
    return { ok: false, message: res.error.message };
  }
  // Saldo novo no painel, no menu de créditos e no extrato
  revalidatePath("/", "layout");
  return { ok: true, order: res.data.order, balance: res.data.balance };
}
