"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { publicValues, type FormState } from "@/lib/form-state";
import { gatewayFetch } from "@/lib/gateway";
import { fieldErrorsOf, formValues, passwordChangeSchema, profileSchema } from "@/lib/validation/auth";

export async function updateProfileAction(_prev: FormState, form: FormData): Promise<FormState> {
  const values = formValues(form);
  const parsed = profileSchema.safeParse(values);
  if (!parsed.success) {
    return { status: "error", fieldErrors: fieldErrorsOf(parsed.error), values: publicValues(values) };
  }

  // Só os campos permitidos vão no corpo (sem mass assignment — #10).
  const res = await gatewayFetch("/api/me", { method: "PATCH", body: { name: parsed.data.name } });
  if (!res.ok) {
    if (res.error.status === 401) redirect("/sessao/expirada");
    return {
      status: "error",
      message: res.error.fieldErrors.name ? undefined : res.error.message,
      fieldErrors: res.error.fieldErrors.name ? { name: res.error.fieldErrors.name } : undefined,
      values: publicValues(values),
    };
  }

  // Atualiza o perfil e o nome exibido na sidebar.
  revalidatePath("/", "layout");
  return { status: "success", message: "Nome atualizado.", values: { name: parsed.data.name } };
}

export async function changePasswordAction(_prev: FormState, form: FormData): Promise<FormState> {
  const values = formValues(form);
  const parsed = passwordChangeSchema.safeParse(values);
  if (!parsed.success) {
    return { status: "error", fieldErrors: fieldErrorsOf(parsed.error) };
  }

  const res = await gatewayFetch("/api/me/password", {
    method: "POST",
    body: { current_password: parsed.data.currentPassword, new_password: parsed.data.newPassword },
  });

  if (!res.ok) {
    const { error } = res;
    if (error.code === "invalid_current_password" || (error.status === 400 && !error.code)) {
      return { status: "error", fieldErrors: { currentPassword: "A senha atual está incorreta." } };
    }
    if (error.status === 401) redirect("/sessao/expirada");
    const fieldErrors: Record<string, string> = {};
    if (error.fieldErrors.new_password) fieldErrors.newPassword = error.fieldErrors.new_password;
    if (error.fieldErrors.current_password) fieldErrors.currentPassword = error.fieldErrors.current_password;
    return {
      status: "error",
      message: Object.keys(fieldErrors).length ? undefined : error.message,
      fieldErrors,
    };
  }

  return {
    status: "success",
    message: "Senha alterada. As outras sessões abertas foram encerradas.",
  };
}
