import "server-only";

/** URL do API Gateway (único backend que a web conhece — ADR-005 / RF21). */
export const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://localhost:8080";

/** Timeout de cada chamada ao gateway (RNF02: a web nunca fica presa num upstream lento). */
export const GATEWAY_TIMEOUT_MS = 8_000;
