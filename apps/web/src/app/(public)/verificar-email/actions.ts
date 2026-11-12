"use server";

import { publicValues, type FormState } from "@/lib/form-state";
import { gatewayFetch } from "@/lib/gateway";
import { fieldErrorsOf, formValues, resendSchema, verifyEmailSchema } from "@/lib/validation/auth";

export async function verifyEmailAction(_prev: FormState, form: FormData): Promise<FormState> {
  const values = formValues(form);
  const parsed = verifyEmailSchema.safeParse(values);
  if (!parsed.success) {
    return { status: "error", fieldErrors: fieldErrorsOf(parsed.error), values: publicValues(values) };
  }

  const res = await gatewayFetch("/api/auth/verify-email", {
    method: "POST",
    auth: false,
    body: parsed.data,
  });

  if (res.ok) return { status: "success", values: publicValues(values) };

  const { error } = res;
  const remaining = error.extra.attempts_remaining;
  let message = error.message;
  if (error.code === "invalid_code" && typeof remaining === "number") {
    message =
      remaining > 0
        ? `Código incorreto. ${remaining === 1 ? "Resta 1 tentativa" : `Restam ${remaining} tentativas`}.`
        : "Código incorreto. Este código foi bloqueado; solicite um novo.";
  } else if (error.status === 400 && !error.code) {
    message = "Código incorreto ou expirado.";
  }

  return {
    status: "error",
    message,
    fieldErrors: error.fieldErrors.code ? { code: error.fieldErrors.code } : undefined,
    values: publicValues(values),
    meta: { code: error.code },
  };
}

export async function resendCodeAction(_prev: FormState, form: FormData): Promise<FormState> {
  const values = formValues(form);
  const parsed = resendSchema.safeParse(values);
  if (!parsed.success) {
    return { status: "error", fieldErrors: fieldErrorsOf(parsed.error), values: publicValues(values) };
  }

  const res = await gatewayFetch("/api/auth/verify-email/resend", {
    method: "POST",
    auth: false,
    body: parsed.data,
  });

  // A API responde 202 sempre (não revela se o e-mail existe). Só 429/indisponibilidade viram erro.
  if (!res.ok && (res.error.status === 429 || res.error.status >= 500)) {
    const wait = res.error.retryAfter;
    return {
      status: "error",
      message: wait ? `Aguarde ${wait} s para pedir outro código.` : res.error.message,
      meta: { retryAfter: wait },
    };
  }
  return { status: "success", message: "Se o e-mail estiver cadastrado, enviamos um novo código." };
}
