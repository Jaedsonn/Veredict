"use client";

import Link from "next/link";
import { useActionState, useState } from "react";

import { PasswordStrength } from "@/components/auth/password-strength";
import { useClientValidation } from "@/components/forms/use-client-validation";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { initialFormState } from "@/lib/form-state";
import { registerSchema } from "@/lib/validation/auth";

import { registerAction } from "./actions";

export function RegisterForm() {
  const [state, formAction, pending] = useActionState(registerAction, initialFormState);
  const { errors, onSubmit } = useClientValidation(registerSchema, state.fieldErrors);
  const [password, setPassword] = useState("");
  const v = state.values ?? {};

  return (
    <form action={formAction} onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      {state.message === "conflict" ? (
        <Alert tone="error" title="Este e-mail já está cadastrado.">
          <Link href="/entrar" className="font-bold underline">
            Entrar
          </Link>{" "}
          ou{" "}
          {/* Recuperação de senha chega na Sprint 2 (#19/#20). */}
          <span title="Disponível em breve">Recuperar senha (em breve)</span>
        </Alert>
      ) : (
        state.message && <Alert tone="error">{state.message}</Alert>
      )}

      <FormField id="name" label="Nome completo:" error={errors.name}>
        <Input name="name" autoComplete="name" defaultValue={v.name} maxLength={120} required />
      </FormField>

      <FormField id="email" label="E-mail:" error={errors.email}>
        <Input name="email" type="email" autoComplete="email" defaultValue={v.email} required />
      </FormField>

      <FormField
        id="password"
        label="Senha:"
        error={errors.password}
        hint={<PasswordStrength value={password} />}
      >
        <PasswordInput
          name="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </FormField>

      <FormField id="confirmPassword" label="Confirmar senha:" error={errors.confirmPassword}>
        <PasswordInput name="confirmPassword" autoComplete="new-password" required />
      </FormField>

      <div className="flex flex-col gap-1.5">
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            name="terms"
            className="mt-0.5 size-5 shrink-0 accent-brand"
            aria-invalid={Boolean(errors.terms) || undefined}
            aria-describedby={errors.terms ? "terms-error" : undefined}
          />
          <span>Li e aceito os termos de uso e a política de privacidade.</span>
        </label>
        {errors.terms && (
          <p id="terms-error" className="text-sm font-medium text-danger">
            {errors.terms}
          </p>
        )}
      </div>

      <Button type="submit" pending={pending} fullWidth>
        Criar conta
      </Button>
    </form>
  );
}
