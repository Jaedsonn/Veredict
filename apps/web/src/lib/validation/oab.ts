/** Inscrição na OAB como o auth aceita (#60): só o formato, sem consulta ao CNA (#64). */

export const OAB_UFS = [
  "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA",
  "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
] as const;

export const OAB_KINDS = [
  { value: "principal", label: "Principal" },
  { value: "suplementar", label: "Suplementar" },
  { value: "transitoria", label: "Transitória" },
] as const;

export type OabUf = (typeof OAB_UFS)[number];
export type OabKind = (typeof OAB_KINDS)[number]["value"];

export const OAB_NUMBER_MESSAGE = "Informe o número da OAB com até 6 dígitos.";
export const OAB_UF_MESSAGE = "Escolha a UF da seccional.";
export const OAB_KIND_MESSAGE = "Escolha o tipo de inscrição.";

/** 1 a 6 dígitos e diferente de zero; zeros à esquerda o auth remove. */
export function isOabNumber(raw: unknown): boolean {
  return typeof raw === "string" && /^\d{1,6}$/.test(raw.trim()) && Number(raw) > 0;
}

export function isOabUf(raw: unknown): raw is OabUf {
  return OAB_UFS.includes(raw as OabUf);
}

export function isOabKind(raw: unknown): raw is OabKind {
  return OAB_KINDS.some((k) => k.value === raw);
}

export function oabKindLabel(kind: string): string {
  return OAB_KINDS.find((k) => k.value === kind)?.label ?? kind;
}
