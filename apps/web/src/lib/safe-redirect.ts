/**
 * Aceita apenas caminhos internos no parâmetro `next`, evitando open redirect (#14).
 * "/perfil" ok; "//evil.com", "https://evil.com", "/\\evil.com" rejeitados.
 */
export function safeNext(next: string | null | undefined, fallback = "/painel"): string {
  if (!next) return fallback;
  if (!next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return fallback;
  return next;
}
