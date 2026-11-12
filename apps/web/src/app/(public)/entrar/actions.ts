"use server";

import { redirect } from "next/navigation";

import { publicValues, type FormState } from "@/lib/form-state";
import { gatewayFetch } from "@/lib/gateway";
import { safeNext } from "@/lib/safe-redirect";
import { setSession } from "@/lib/session";
import type { TokenPair } from "@/lib/tokens";
import { fieldErrorsOf, formValues, loginSchema } from "@/lib/validation/auth";

export async function loginAction(_prev: FormState, form: FormData): Promise<FormState> {
  const values = formValues(form);
  const parsed = loginSchema.safeParse(values);
  if (!parsed.success) {
    return { status: "error", fieldErrors: fieldErrorsOf(parsed.error), values: publicValues(values) };
  }

  const res = await gatewayFetch<TokenPair>("/api/auth/login", {
    method: "POST",
    auth: false,
    body: parsed.data,
  });

  if (!res.ok) {
    const { error } = res;
    if (error.status === 403 && error.code === "email_not_verified") {
      redirect(`/verificar-email?email=${encodeURIComponent(parsed.data.email)}`);
    }
    let message = error.message;
    if (error.status === 401) message = "E-mail ou senha incorretos.";
    if (error.status === 429) {
      message = error.retryAfter
        ? `Muitas tentativas, tente em ${error.retryAfter} s.`
        : "Muitas tentativas, tente novamente em instantes.";
    }
    return { status: "error", message, values: publicValues(values) };
  }

  await setSession(res.data);
  redirect(safeNext(values.next));
}
