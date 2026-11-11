"use client";

import { useSearchParams } from "next/navigation";
import { useActionState } from "react";

import { useClientValidation } from "@/components/forms/use-client-validation";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { initialFormState } from "@/lib/form-state";
import { loginSchema } from "@/lib/validation/auth";

import { loginAction } from "./actions";

export function LoginForm() {
  const params = useSearchParams();
  const [state, formAction, pending] = useActionState(loginAction, initialFormState);
  const { errors, onSubmit } = useClientValidation(loginSchema, state.fieldErrors);

  const expired = params.get("expirado") === "1";
  const next = params.get("next") ?? "";
  const email = state.values?.email ?? params.get("email") ?? "";

  return (
    <form action={formAction} onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      {state.message ? (
        <Alert tone="error">{state.message}</Alert>
      ) : (
        expired && <Alert tone="info">Sua sessão expirou. Entre novamente.</Alert>
      )}

      {/* Validado de novo no servidor (safeNext) para evitar open redirect. */}
      <input type="hidden" name="next" value={next} />

      <FormField id="email" label="E-mail:" error={errors.email}>
        <Input name="email" type="email" autoComplete="username" defaultValue={email} required />
      </FormField>

      <FormField id="password" label="Senha:" error={errors.password}>
        <PasswordInput name="password" autoComplete="current-password" required />
      </FormField>

      <Button type="submit" pending={pending} fullWidth>
        Entrar
      </Button>
    </form>
  );
}
