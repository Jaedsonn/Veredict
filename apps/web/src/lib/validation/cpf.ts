/**
 * CPF no navegador: mesma regra do value object `Cpf` do auth (#60), com os mesmos
 * vetores de teste (`cpf-vectors.json`). O servidor valida de novo.
 */

// Com ou sem máscara, mas sem misturar outros separadores
const CPF_FORMAT = /^\d{3}\.?\d{3}\.?\d{3}-?\d{2}$/;

function checkDigit(digits: string): number {
  let total = 0;
  for (let i = 0; i < digits.length; i++) total += Number(digits[i]) * (digits.length + 1 - i);
  return ((total * 10) % 11) % 10;
}

/** Os 11 dígitos de um CPF válido, ou `null` se o formato ou os dígitos verificadores falharem. */
export function cpfDigits(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const cleaned = raw.trim();
  if (!CPF_FORMAT.test(cleaned)) return null;
  const digits = cleaned.replace(/[.-]/g, "");
  if (/^(\d)\1{10}$/.test(digits)) return null;
  const first = checkDigit(digits.slice(0, 9));
  const second = checkDigit(digits.slice(0, 9) + first);
  return digits.slice(9) === `${first}${second}` ? digits : null;
}

/** `***.982.247-**`: o formato que o `/me` devolve em `cpf_masked`. */
export function hideCpf(digits: string): string {
  return `***.${digits.slice(3, 6)}.${digits.slice(6, 9)}-**`;
}

/** Máscara progressiva do campo: `52998` vira `529.98`, e só entram até 11 dígitos. */
export function formatCpfInput(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 11);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`;
  if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`;
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}
