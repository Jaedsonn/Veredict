"use server";

import { redirect } from "next/navigation";

import { publicValues, type FormState } from "@/lib/form-state";
import { gatewayFetch } from "@/lib/gateway";
import { fieldErrorsOf, formValues, registerSchema } from "@/lib/validation/auth";

/** Mapeia os nomes de campo da API (snake_case) para os do formulário. */
const API_FIELDS: Record<string, string> = { name: "name", email: "email", password: "password" };

export async function registerAction(_prev: FormState, form: FormData): Promise<FormState> {
  const values = formValues(form);
  const parsed = registerSchema.safeParse(values);
  if (!parsed.success) {
    return { status: "error", fieldErrors: fieldErrorsOf(parsed.error), values: publicValues(values) };
  }

  const { name, email, password } = parsed.data;
  const res = await gatewayFetch("/api/auth/register", {
    method: "POST",
    auth: false,
    body: { name, email, password },
  });

  if (!res.ok) {
    const { error } = res;
    if (error.status === 409) {
      return { status: "error", message: "conflict", values: publicValues(values) };
    }
    const fieldErrors: Record<string, string> = {};
    for (const [k, v] of Object.entries(error.fieldErrors)) fieldErrors[API_FIELDS[k] ?? k] = v;
    return {
      status: "error",
      message: Object.keys(fieldErrors).length ? undefined : error.message,
      fieldErrors,
      values: publicValues(values),
    };
  }

  redirect(`/verificar-email?email=${encodeURIComponent(email)}`);
}
