import { z } from "zod";

import { cpfDigits } from "@/lib/validation/cpf";
import {
  OAB_KIND_MESSAGE,
  OAB_NUMBER_MESSAGE,
  OAB_UF_MESSAGE,
  isOabKind,
  isOabNumber,
  isOabUf,
} from "@/lib/validation/oab";

/**
 * Schemas compartilhados entre o formulário (cliente) e a Server Action (servidor).
 * As regras espelham a API do serviço de autenticação (#7, #8, #9, #10, #19, #60).
 */

export const PASSWORD_MIN = 10;

export const passwordRules = [
  { id: "length", label: `Pelo menos ${PASSWORD_MIN} caracteres`, test: (v: string) => v.length >= PASSWORD_MIN },
  { id: "letter", label: "Pelo menos 1 letra", test: (v: string) => /\p{L}/u.test(v) },
  { id: "number", label: "Pelo menos 1 número", test: (v: string) => /\d/.test(v) },
] as const;

export const passwordSchema = z
  .string()
  .min(PASSWORD_MIN, `A senha deve ter pelo menos ${PASSWORD_MIN} caracteres.`)
  .max(128, "A senha deve ter no máximo 128 caracteres.")
  .refine((v) => /\p{L}/u.test(v), "A senha deve conter pelo menos 1 letra.")
  .refine((v) => /\d/.test(v), "A senha deve conter pelo menos 1 número.");

const emailSchema = z
  .string()
  .trim()
  .toLowerCase()
  .min(1, "Informe seu e-mail.")
  .pipe(z.email("Informe um e-mail válido."));

const nameSchema = z
  .string()
  .trim()
  .min(1, "Informe seu nome.")
  .max(120, "O nome deve ter no máximo 120 caracteres.");

/**
 * Por padrão o zod 4 só roda o refine do objeto quando todos os campos são válidos.
 * `when` faz a checagem de confirmação rodar assim que os dois campos existem,
 * para o usuário ver todos os erros de uma vez.
 */
function bothStrings(a: string, b: string) {
  return (payload: z.core.ParsePayload) => {
    const v = payload.value as Record<string, unknown> | null;
    return typeof v?.[a] === "string" && typeof v?.[b] === "string";
  };
}

export const USER_TYPES = ["common", "lawyer"] as const;
export type UserType = (typeof USER_TYPES)[number];

/** O bloco da OAB só vale para advogado; para conta comum os campos são ignorados. */
function isLawyer(payload: z.core.ParsePayload) {
  return (payload.value as Record<string, unknown> | null)?.userType === "lawyer";
}

/**
 * Discriminado pelo `userType`: advogado precisa dos três campos da OAB. Os campos
 * ficam planos no formulário e a Server Action monta o `oab` aninhado da API.
 */
export const registerSchema = z
  .object({
    name: nameSchema,
    email: emailSchema,
    password: passwordSchema,
    confirmPassword: z.string().min(1, "Confirme sua senha."),
    userType: z.enum(USER_TYPES, "Escolha o tipo de conta."),
    cpf: z
      .string("CPF inválido.")
      .refine((v) => cpfDigits(v) !== null, "CPF inválido.")
      .transform((v) => cpfDigits(v) ?? ""),
    oabNumber: z.string().optional(),
    oabUf: z.string().optional(),
    oabKind: z.string().optional(),
    terms: z.literal("on", "Você precisa aceitar os termos de uso."),
  })
  .refine((d) => d.password === d.confirmPassword, {
    path: ["confirmPassword"],
    message: "As senhas não coincidem.",
    when: bothStrings("password", "confirmPassword"),
  })
  .refine((d) => isOabNumber(d.oabNumber), {
    path: ["oabNumber"],
    message: OAB_NUMBER_MESSAGE,
    when: isLawyer,
  })
  .refine((d) => isOabUf(d.oabUf), { path: ["oabUf"], message: OAB_UF_MESSAGE, when: isLawyer })
  .refine((d) => isOabKind(d.oabKind), {
    path: ["oabKind"],
    message: OAB_KIND_MESSAGE,
    when: isLawyer,
  });

export const verifyEmailSchema = z.object({
  email: emailSchema,
  code: z.string().regex(/^\d{6}$/, "Digite os 6 dígitos do código."),
});

export const resendSchema = z.object({ email: emailSchema });

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, "Informe sua senha."),
});

export const profileSchema = z.object({ name: nameSchema });

export const forgotPasswordSchema = z.object({ email: emailSchema });

/** Formato do `secrets.token_urlsafe(32)` do auth: 43 caracteres base64url. */
export const RESET_TOKEN_RE = /^[A-Za-z0-9_-]{43}$/;

export const resetPasswordSchema = z
  .object({
    token: z.string().regex(RESET_TOKEN_RE, "Link inválido ou expirado. Solicite um novo."),
    newPassword: passwordSchema,
    confirmPassword: z.string().min(1, "Confirme a nova senha."),
  })
  .refine((d) => d.newPassword === d.confirmPassword, {
    path: ["confirmPassword"],
    message: "As senhas não coincidem.",
    when: bothStrings("newPassword", "confirmPassword"),
  });

export const passwordChangeSchema = z
  .object({
    currentPassword: z.string().min(1, "Informe sua senha atual."),
    newPassword: passwordSchema,
    confirmPassword: z.string().min(1, "Confirme a nova senha."),
  })
  .refine((d) => d.newPassword === d.confirmPassword, {
    path: ["confirmPassword"],
    message: "As senhas não coincidem.",
    when: bothStrings("newPassword", "confirmPassword"),
  })
  .refine((d) => d.newPassword !== d.currentPassword, {
    path: ["newPassword"],
    message: "A nova senha deve ser diferente da atual.",
    when: bothStrings("newPassword", "currentPassword"),
  });

/** Primeiro erro de cada campo, no formato usado pelos formulários. */
export function fieldErrorsOf(error: z.ZodError): Record<string, string> {
  const out: Record<string, string> = {};
  for (const issue of error.issues) {
    const key = issue.path.join(".");
    if (key && !out[key]) out[key] = issue.message;
  }
  return out;
}

export function formValues(form: FormData): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of form.entries()) if (typeof v === "string") out[k] = v;
  return out;
}
