import { z } from "zod";

import { cpfDigits } from "@/lib/validation/cpf";
import { OAB_UFS } from "@/lib/validation/oab";

/**
 * Dados da compra do Apêndice A (REQ05). Mesmas regras e mensagens do serviço de
 * pagamento (`services/payment/src/payment_service/schemas.py`); o servidor valida de novo.
 */

/** As 27 UFs: a lista é a mesma das seccionais da OAB. */
export const UFS = OAB_UFS;
export type Uf = (typeof UFS)[number];

/** DDD + número (10 ou 11 dígitos), aceitando máscara e +55. */
export function phoneDigits(raw: string): string | null {
  const cleaned = raw.trim();
  if (!cleaned || !/^[\d\s()+-]+$/.test(cleaned)) return null;
  let digits = cleaned.replace(/\D/g, "");
  if ((digits.length === 12 || digits.length === 13) && digits.startsWith("55")) digits = digits.slice(2);
  if (!/^\d{10,11}$/.test(digits) || digits.startsWith("0")) return null;
  return digits;
}

export function cepDigits(raw: string): string | null {
  const cleaned = raw.trim();
  return /^\d{5}-?\d{3}$/.test(cleaned) ? cleaned.replace("-", "") : null;
}

/** Máscara progressiva do telefone: `(71) 99876-5432` ou `(71) 3333-4444`. */
export function formatPhoneInput(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 11);
  if (d.length <= 2) return d.length ? `(${d}` : "";
  const ddd = `(${d.slice(0, 2)}) `;
  const rest = d.slice(2);
  if (rest.length <= 4) return ddd + rest;
  const split = rest.length === 9 ? 5 : 4;
  return `${ddd}${rest.slice(0, split)}-${rest.slice(split)}`;
}

/** Máscara progressiva do CEP: `40110-100`. */
export function formatCepInput(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 8);
  return d.length <= 5 ? d : `${d.slice(0, 5)}-${d.slice(5)}`;
}

function text(message: string, max: number) {
  return z.string(message).trim().min(1, message).max(max, `Use no máximo ${max} caracteres.`);
}

export const billingSchema = z.object({
  name: text("Informe o nome completo.", 120),
  email: z
    .string("Informe um e-mail válido.")
    .trim()
    .toLowerCase()
    .max(255, "Use no máximo 255 caracteres.")
    .pipe(z.email("Informe um e-mail válido.")),
  phone: z
    .string("Informe o telefone com DDD.")
    .refine((v) => phoneDigits(v) !== null, "Informe o telefone com DDD.")
    .transform((v) => phoneDigits(v) ?? ""),
  cpf: z
    .string("Informe o CPF.")
    .trim()
    .min(1, "Informe o CPF.")
    .refine((v) => cpfDigits(v) !== null, "CPF inválido.")
    .transform((v) => cpfDigits(v) ?? ""),
  cep: z
    .string("Informe o CEP com 8 dígitos.")
    .refine((v) => cepDigits(v) !== null, "Informe o CEP com 8 dígitos.")
    .transform((v) => cepDigits(v) ?? ""),
  street: text("Informe o endereço.", 120),
  number: text("Informe o número (ou S/N).", 10),
  complement: z
    .string()
    .trim()
    .max(60, "Use no máximo 60 caracteres.")
    .optional()
    .transform((v) => v || null),
  district: text("Informe o bairro.", 60),
  city: text("Informe a cidade.", 60),
  state: z.enum(UFS, "Escolha o estado."),
});

export type BillingInput = z.output<typeof billingSchema>;

/** Campos do formulário, na ordem da tela, para mapear os erros da API (`billing.<campo>`). */
export const BILLING_FIELDS = [
  "name",
  "email",
  "phone",
  "cpf",
  "cep",
  "street",
  "number",
  "complement",
  "district",
  "city",
  "state",
] as const;
