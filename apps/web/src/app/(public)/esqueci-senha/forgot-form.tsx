"use client";

import Link from "next/link";
import { useActionState } from "react";

import { useClientValidation } from "@/components/forms/use-client-validation";
import { Alert } from "@/components/ui/alert";
import { Button, buttonClasses } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { initialFormState } from "@/lib/form-state";
import { forgotPasswordSchema } from "@/lib/validation/auth";

import { forgotPasswordAction } from "./actions";

export function ForgotPasswordForm() {
  const [state, formAction, pending] = useActionState(forgotPasswordAction, initialFormState);
  const { errors, onSubmit } = useClientValidation(forgotPasswordSchema, state.fieldErrors);

  if (state.status === "success") {
    return (
      <div className="flex flex-col gap-5">
        {/* Mensagem neutra: não revela se o e-mail tem conta (#19). */}
        <Alert tone="success" title="Pedido recebido.">
          Se existir uma conta com este e-mail, enviaremos um link para redefinir a senha. Ele vale por
          30 minutos e só pode ser usado uma vez.
        </Alert>
        <Link href="/entrar" className={buttonClasses("secondary", true)}>
          Voltar para o login
        </Link>
      </div>
    );
  }

  return (
    <form action={formAction} onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      {state.message && <Alert tone="error">{state.message}</Alert>}

      <FormField id="email" label="E-mail:" error={errors.email}>
        <Input name="email" type="email" autoComplete="email" defaultValue={state.values?.email} required />
      </FormField>

      <Button type="submit" pending={pending} fullWidth>
        Enviar link
      </Button>
    </form>
  );
}
