const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

/** Valores chegam em centavos inteiros da API (#21): nunca float no caminho. */
export function formatBRL(cents: number): string {
  return brl.format(cents / 100);
}

export function creditsLabel(n: number): string {
  return `${n} ${Math.abs(n) === 1 ? "crédito" : "créditos"}`;
}
