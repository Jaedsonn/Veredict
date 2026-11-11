"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useActionState, useEffect, useState } from "react";

import { useClientValidation } from "@/components/forms/use-client-validation";
import { Alert } from "@/components/ui/alert";
import { Button, buttonClasses } from "@/components/ui/button";
import { CardTitle } from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { OtpInput } from "@/components/ui/otp-input";
import { initialFormState } from "@/lib/form-state";
import { verifyEmailSchema } from "@/lib/validation/auth";

import { resendCodeAction, verifyEmailAction } from "./actions";

const RESEND_COOLDOWN_S = 60;

function useCountdown(initial: number) {
  const [left, setLeft] = useState(initial);
  useEffect(() => {
    if (left <= 0) return;
    const t = setTimeout(() => setLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [left]);
  return [left, setLeft] as const;
}

export function VerifyEmailForm() {
  const params = useSearchParams();
  const emailFromUrl = params.get("email") ?? "";

  const [state, verify, verifying] = useActionState(verifyEmailAction, initialFormState);
  const [resendState, resend, resending] = useActionState(resendCodeAction, initialFormState);
  const { errors, onSubmit } = useClientValidation(verifyEmailSchema, state.fieldErrors);

  // O código acabou de ser enviado no cadastro: o reenvio só libera após 60 s.
  const [cooldown, setCooldown] = useCountdown(emailFromUrl ? RESEND_COOLDOWN_S : 0);
  const [handledResend, setHandledResend] = useState(resendState);
  if (resendState !== handledResend) {
    setHandledResend(resendState);
    const wait = resendState.meta?.retryAfter;
    if (resendState.status === "success") setCooldown(RESEND_COOLDOWN_S);
    else if (typeof wait === "number") setCooldown(wait);
  }

  const email = state.values?.email ?? emailFromUrl;

  if (state.status === "success") {
    return (
      <div className="flex flex-col gap-5">
        <CardTitle as="h1">E-mail confirmado!</CardTitle>
        <Alert tone="success">Sua conta está ativa. Agora é só entrar.</Alert>
        <Link
          href={`/entrar?email=${encodeURIComponent(email)}`}
          className={buttonClasses("primary", true)}
        >
          Entrar
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <CardTitle as="h1">Verifique seu e-mail</CardTitle>
        <p className="text-sm text-muted-foreground">
          {email ? (
            <>
              Enviamos um código de 6 dígitos para <strong className="text-foreground">{email}</strong>. Ele
              vale por 15 minutos.
            </>
          ) : (
            "Informe seu e-mail e o código de 6 dígitos que enviamos."
          )}
        </p>
      </div>

      {state.message && <Alert tone="error">{state.message}</Alert>}

      <form action={verify} onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
        {emailFromUrl ? (
          <input type="hidden" name="email" value={email} />
        ) : (
          <FormField id="email" label="E-mail:" error={errors.email}>
            <Input name="email" type="email" autoComplete="email" defaultValue={email} required />
          </FormField>
        )}

        <div className="flex flex-col gap-1.5">
          <OtpInput
            name="code"
            invalid={Boolean(errors.code) || state.status === "error"}
            describedBy={errors.code ? "code-error" : undefined}
          />
          {errors.code && (
            <p id="code-error" className="text-sm font-medium text-danger">
              {errors.code}
            </p>
          )}
        </div>

        <Button type="submit" pending={verifying} fullWidth>
          Confirmar código
        </Button>
      </form>

      <form action={resend} className="flex flex-col items-center gap-2 text-sm">
        <input type="hidden" name="email" value={email} />
        {resendState.message && (
          <p role="status" className={resendState.status === "error" ? "text-danger" : "text-success"}>
            {resendState.message}
          </p>
        )}
        <Button type="submit" variant="ghost" pending={resending} disabled={cooldown > 0 || !email}>
          {cooldown > 0 ? `Reenviar código em ${cooldown} s` : "Reenviar código"}
        </Button>
      </form>
    </div>
  );
}
