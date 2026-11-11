/** Estado devolvido pelas Server Actions para `useActionState`. */
export type FormState = {
  status: "idle" | "error" | "success";
  message?: string;
  fieldErrors?: Record<string, string>;
  /** Valores digitados (sem senhas) para repopular o formulário após erro. */
  values?: Record<string, string>;
  /** Dados extras da resposta (ex.: tentativas restantes). */
  meta?: Record<string, unknown>;
};

export const initialFormState: FormState = { status: "idle" };

/** Remove campos sensíveis antes de devolver os valores ao navegador. */
export function publicValues(values: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(values)) {
    if (/password|senha|code|token/i.test(k) || k.startsWith("$")) continue;
    out[k] = v;
  }
  return out;
}
