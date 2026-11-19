"use server";

import { publicValues, type FormState } from "@/lib/form-state";
import { gatewayFetch } from "@/lib/gateway";
import { fieldErrorsOf, forgotPasswordSchema, formValues } from "@/lib/validation/auth";

export async function forgotPasswordAction(_prev: FormState, form: FormData): Promise<FormState> {
  const values = formValues(form);
  const parsed = forgotPasswordSchema.safeParse(values);
  if (!parsed.success) {
    return { status: "error", fieldErrors: fieldErrorsOf(parsed.error), values: publicValues(values) };
  }

  const res = await gatewayFetch("/api/auth/password/forgot", {
    method: "POST",
    auth: false,
    body: parsed.data,
  });

  // A API responde 202 exista a conta ou não (#19). Só 429/indisponibilidade viram erro.
  if (!res.ok && (res.error.status === 429 || res.error.status >= 500)) {
    const wait = res.error.retryAfter;
    return {
      status: "error",
      message: wait
        ? `Muitos pedidos de redefinição. Tente novamente em ${Math.ceil(wait / 60)} min.`
        : res.error.message,
      values: publicValues(values),
    };
  }
  if (!res.ok && res.error.fieldErrors.email) {
    return { status: "error", fieldErrors: { email: res.error.fieldErrors.email }, values: publicValues(values) };
  }
  return { status: "success", values: publicValues(values) };
}
