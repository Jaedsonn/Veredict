"use client";

import { useState, type FormEvent } from "react";
import type { z } from "zod";

import { fieldErrorsOf, formValues } from "@/lib/validation/auth";

/**
 * Valida no navegador com o MESMO schema zod da Server Action (#12).
 * Se houver erro, bloqueia o envio e mostra os erros por campo; o servidor
 * valida de novo de qualquer forma (o cliente nunca é confiável).
 */
export function useClientValidation(schema: z.ZodType, serverErrors?: Record<string, string>) {
  const [clientErrors, setClientErrors] = useState<Record<string, string> | null>(null);
  const [lastServerErrors, setLastServerErrors] = useState(serverErrors);

  // Nova resposta do servidor substitui os erros locais.
  if (serverErrors !== lastServerErrors) {
    setLastServerErrors(serverErrors);
    setClientErrors(null);
  }

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    const result = schema.safeParse(formValues(new FormData(e.currentTarget)));
    if (!result.success) {
      e.preventDefault();
      const errors = fieldErrorsOf(result.error);
      setClientErrors(errors);
      const first = Object.keys(errors)[0];
      if (first) e.currentTarget.querySelector<HTMLElement>(`[name="${first}"]`)?.focus();
    } else {
      setClientErrors(null);
    }
  }

  return { errors: clientErrors ?? serverErrors ?? {}, onSubmit };
}
