"use server";

import { type FormState } from "@/lib/form-state";
import { gatewayFetch } from "@/lib/gateway";
import { clearSession } from "@/lib/session";
import { fieldErrorsOf, formValues, resetPasswordSchema } from "@/lib/validation/auth";

export async function resetPasswordAction(_prev: FormState, form: FormData): Promise<FormState> {
  const parsed = resetPasswordSchema.safeParse(formValues(form));
  if (!parsed.success) {
    const fieldErrors = fieldErrorsOf(parsed.error);
    // Token fora do formato: o mesmo aviso de link inválido da API.
    if (fieldErrors.token) return { status: "error", meta: { code: "invalid_reset_token" } };
    return { status: "error", fieldErrors };
  }

  const res = await gatewayFetch("/api/auth/password/reset", {
    method: "POST",
    auth: false,
    body: { token: parsed.data.token, new_password: parsed.data.newPassword },
  });

  if (!res.ok) {
    const { error } = res;
    if (error.code === "invalid_reset_token" || (error.status === 400 && !error.code)) {
      return { status: "error", meta: { code: "invalid_reset_token" } };
    }
    if (error.fieldErrors.new_password) {
      return { status: "error", fieldErrors: { newPassword: error.fieldErrors.new_password } };
    }
    let message = error.message;
    if (error.status === 429) {
      message = error.retryAfter
        ? `Muitas tentativas. Tente novamente em ${Math.ceil(error.retryAfter / 60)} min.`
        : "Muitas tentativas. Aguarde um pouco e tente novamente.";
    }
    return { status: "error", message };
  }

  // O auth revogou todas as sessões; um cookie antigo neste navegador não vale mais.
  await clearSession();
  return { status: "success" };
}
