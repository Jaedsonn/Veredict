export const services = {
  users: process.env.USERS_API_URL ?? "http://localhost:8001",
} as const;

export type ServiceName = keyof typeof services;

export async function serviceFetch(
  service: ServiceName,
  path: string,
  init?: RequestInit,
): Promise<Response> {
  return fetch(new URL(path, services[service]), {
    ...init,
    signal: init?.signal ?? AbortSignal.timeout(3_000),
  });
}
