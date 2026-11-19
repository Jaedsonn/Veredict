"use server";

import { redirect } from "next/navigation";

import { publicValues, type FormState } from "@/lib/form-state";
import { gatewayFetch } from "@/lib/gateway";
import { fieldErrorsOf, formValues, registerSchema } from "@/lib/validation/auth";

/** Mapeia os campos da API (snake_case, `oab` aninhado) para os do formulário. */
const API_FIELDS: Record<string, string> = {
  name: "name",
  email: "email",
  password: "password",
  user_type: "userType",
  cpf: "cpf",
  oab: "oabNumber",
  "oab.number": "oabNumber",
  "oab.uf": "oabUf",
  "oab.kind": "oabKind",
};

/** O 409 vem com um `code` por campo (#60); o de e-mail mantém o alerta com links. */
const CONFLICT_FIELDS: Record<string, string> = {
  cpf_already_registered: "cpf",
  oab_already_registered: "oabNumber",
};

export async function registerAction(_prev: FormState, form: FormData): Promise<FormState> {
  const values = formValues(form);
  const parsed = registerSchema.safeParse(values);
  if (!parsed.success) {
    return { status: "error", fieldErrors: fieldErrorsOf(parsed.error), values: publicValues(values) };
  }

  const { name, email, password, userType, cpf, oabNumber, oabUf, oabKind } = parsed.data;
  const res = await gatewayFetch("/api/auth/register", {
    method: "POST",
    auth: false,
    body: {
      name,
      email,
      password,
      user_type: userType,
      cpf,
      ...(userType === "lawyer" ? { oab: { number: oabNumber, uf: oabUf, kind: oabKind } } : {}),
    },
  });

  if (!res.ok) {
    const { error } = res;
    if (error.status === 409) {
      const field = error.code ? CONFLICT_FIELDS[error.code] : undefined;
      if (field) {
        return { status: "error", fieldErrors: { [field]: error.message }, values: publicValues(values) };
      }
      return { status: "error", message: "conflict", values: publicValues(values) };
    }
    const fieldErrors: Record<string, string> = {};
    for (const [k, v] of Object.entries(error.fieldErrors)) {
      const field = API_FIELDS[k] ?? k;
      if (!fieldErrors[field]) fieldErrors[field] = v;
    }
    return {
      status: "error",
      message: Object.keys(fieldErrors).length ? undefined : error.message,
      fieldErrors,
      values: publicValues(values),
    };
  }

  redirect(`/verificar-email?email=${encodeURIComponent(email)}`);
}
