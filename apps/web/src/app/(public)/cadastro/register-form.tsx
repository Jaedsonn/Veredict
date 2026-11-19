"use client";

import Link from "next/link";
import { startTransition, useActionState, useState, type FormEvent } from "react";

import { PasswordStrength } from "@/components/auth/password-strength";
import { useClientValidation } from "@/components/forms/use-client-validation";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Select } from "@/components/ui/select";
import { initialFormState } from "@/lib/form-state";
import { registerSchema, type UserType } from "@/lib/validation/auth";
import { cpfDigits, cpfLiveError, formatCpfInput } from "@/lib/validation/cpf";
import { OAB_KINDS, OAB_UFS } from "@/lib/validation/oab";

import { registerAction } from "./actions";

const USER_TYPE_OPTIONS: { value: UserType; label: string; hint: string }[] = [
  { value: "common", label: "Pessoa", hint: "Para acompanhar seus próprios processos." },
  { value: "lawyer", label: "Advogado(a)", hint: "Informe sua inscrição na OAB." },
];

export function RegisterForm() {
  const [state, formAction, pending] = useActionState(registerAction, initialFormState);
  const { errors, onSubmit } = useClientValidation(registerSchema, state.fieldErrors);
  const [password, setPassword] = useState("");
  const v = state.values ?? {};
  // Controlados: o CPF não volta do servidor (publicValues) e o tipo decide o bloco da OAB
  const [userType, setUserType] = useState<UserType>(v.userType === "lawyer" ? "lawyer" : "common");
  const [cpf, setCpf] = useState("");
  const [cpfBlurred, setCpfBlurred] = useState(false);
  // CPF do último envio: o erro do envio (inclusive "já cadastrado") some quando o CPF muda
  const [submittedCpf, setSubmittedCpf] = useState<string | null>(null);
  const [oabUf, setOabUf] = useState(v.oabUf ?? "");
  const [oabKind, setOabKind] = useState(v.oabKind ?? "principal");

  const cpfError = cpfLiveError(cpf, cpfBlurred) ?? (cpf === submittedCpf ? errors.cpf : undefined);
  const cpfOk = !cpfError && cpfDigits(cpf) !== null;

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    setSubmittedCpf(cpf);
    onSubmit(e);
    if (e.defaultPrevented) return;
    // Sem o reset automático do <form action>: ele desmarcaria o rádio e os selects controlados
    // depois de um erro do servidor, com o bloco da OAB ainda na tela
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    startTransition(() => formAction(data));
  }

  return (
    <form action={formAction} onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
      {state.message === "conflict" ? (
        <Alert tone="error" title="Este e-mail já está cadastrado.">
          <Link href="/entrar" className="font-bold underline">
            Entrar
          </Link>{" "}
          ou{" "}
          <Link href="/esqueci-senha" className="font-bold underline">
            Recuperar senha
          </Link>
        </Alert>
      ) : (
        state.message && <Alert tone="error">{state.message}</Alert>
      )}

      <fieldset
        className="flex flex-col gap-2"
        aria-describedby={errors.userType ? "userType-error" : undefined}
      >
        <legend className="label-mono mb-2">Tipo de conta:</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {USER_TYPE_OPTIONS.map((option) => (
            <label
              key={option.value}
              className="flex cursor-pointer items-start gap-3 rounded-input border-2 border-transparent bg-white p-3 has-[:checked]:border-brand"
            >
              <input
                type="radio"
                name="userType"
                value={option.value}
                checked={userType === option.value}
                onChange={() => setUserType(option.value)}
                className="mt-1 size-4 shrink-0 accent-brand"
              />
              <span className="flex flex-col">
                <span className="font-bold">{option.label}</span>
                <span className="text-sm text-muted-foreground">{option.hint}</span>
              </span>
            </label>
          ))}
        </div>
        {errors.userType && (
          <p id="userType-error" className="text-sm font-medium text-danger">
            {errors.userType}
          </p>
        )}
      </fieldset>

      <FormField id="name" label="Nome completo:" error={errors.name}>
        <Input name="name" autoComplete="name" defaultValue={v.name} maxLength={120} required />
      </FormField>

      <FormField id="email" label="E-mail:" error={errors.email}>
        <Input name="email" type="email" autoComplete="email" defaultValue={v.email} required />
      </FormField>

      <FormField
        id="cpf"
        label="CPF:"
        error={cpfError}
        hint={cpfOk ? <span className="text-success">CPF válido.</span> : undefined}
      >
        <Input
          name="cpf"
          inputMode="numeric"
          autoComplete="off"
          placeholder="000.000.000-00"
          maxLength={14}
          value={cpf}
          onChange={(e) => setCpf(formatCpfInput(e.target.value))}
          onBlur={() => setCpfBlurred(true)}
          required
        />
      </FormField>

      {userType === "lawyer" && (
        <fieldset className="flex flex-col gap-4 rounded-input border-2 border-brand/20 p-4">
          <legend className="label-mono">Inscrição na OAB:</legend>
          <div className="grid gap-4 sm:grid-cols-[2fr_1fr]">
            <FormField id="oabNumber" label="Número:" error={errors.oabNumber}>
              <Input
                name="oabNumber"
                inputMode="numeric"
                pattern="[0-9]*"
                autoComplete="off"
                maxLength={6}
                defaultValue={v.oabNumber}
                required
              />
            </FormField>
            <FormField id="oabUf" label="UF:" error={errors.oabUf}>
              <Select name="oabUf" value={oabUf} onChange={(e) => setOabUf(e.target.value)} required>
                <option value="" disabled>
                  UF
                </option>
                {OAB_UFS.map((uf) => (
                  <option key={uf} value={uf}>
                    {uf}
                  </option>
                ))}
              </Select>
            </FormField>
          </div>
          <FormField id="oabKind" label="Tipo de inscrição:" error={errors.oabKind}>
            <Select
              name="oabKind"
              value={oabKind}
              onChange={(e) => setOabKind(e.target.value)}
              required
            >
              {OAB_KINDS.map((kind) => (
                <option key={kind.value} value={kind.value}>
                  {kind.label}
                </option>
              ))}
            </Select>
          </FormField>
          <p className="text-sm text-muted-foreground">
            Por enquanto conferimos só o formato; a inscrição fica registrada como informada por você.
          </p>
        </fieldset>
      )}

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
