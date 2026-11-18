"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useActionState, useState } from "react";

import { PasswordStrength } from "@/components/auth/password-strength";
import { useClientValidation } from "@/components/forms/use-client-validation";
import { Alert } from "@/components/ui/alert";
import { Button, buttonClasses } from "@/components/ui/button";
import { CardTitle } from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { PasswordInput } from "@/components/ui/password-input";
import { initialFormState } from "@/lib/form-state";
import { RESET_TOKEN_RE, resetPasswordSchema } from "@/lib/validation/auth";

import { resetPasswordAction } from "./actions";

function InvalidLink() {
  return (
    <div className="flex flex-col gap-5">
      <CardTitle as="h1">Link inválido ou expirado</CardTitle>
      <Alert tone="error">
        Este link de redefinição não vale mais. Ele expira em 30 minutos, só pode ser usado uma vez e deixa de
        valer quando você pede outro.
      </Alert>
      <Link href="/esqueci-senha" className={buttonClasses("primary", true)}>
        Pedir um novo link
      </Link>
    </div>
  );
}

export function ResetPasswordForm() {
  const params = useSearchParams();
  // O token só circula no formulário; nunca é logado nem vai para outra URL.
  const token = params.get("token") ?? "";

  const [state, formAction, pending] = useActionState(resetPasswordAction, initialFormState);
  const { errors, onSubmit } = useClientValidation(resetPasswordSchema, state.fieldErrors);
  const [newPassword, setNewPassword] = useState("");

  if (!RESET_TOKEN_RE.test(token) || state.meta?.code === "invalid_reset_token") return <InvalidLink />;

  if (state.status === "success") {
    return (
      <div className="flex flex-col gap-5">
        <CardTitle as="h1">Senha redefinida!</CardTitle>
        <Alert tone="success">
          Sua nova senha já vale. Por segurança, encerramos todas as sessões abertas: entre de novo em cada
          dispositivo.
        </Alert>
        <Link href="/entrar" className={buttonClasses("primary", true)}>
          Entrar
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <CardTitle as="h1">Criar nova senha</CardTitle>
        <p className="text-sm text-muted-foreground">Escolha uma senha que você não usa em outros sites.</p>
      </div>

      <form action={formAction} onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
        {state.message && <Alert tone="error">{state.message}</Alert>}

        <input type="hidden" name="token" value={token} />

        <FormField
          id="newPassword"
          label="Nova senha:"
          error={errors.newPassword}
          hint={<PasswordStrength value={newPassword} />}
        >
          <PasswordInput
            name="newPassword"
            autoComplete="new-password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
        </FormField>

        <FormField id="confirmPassword" label="Confirmar nova senha:" error={errors.confirmPassword}>
          <PasswordInput name="confirmPassword" autoComplete="new-password" required />
        </FormField>

        <Button type="submit" pending={pending} fullWidth>
          Redefinir senha
        </Button>
      </form>
    </div>
  );
}
