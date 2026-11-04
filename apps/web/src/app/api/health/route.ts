import { serviceFetch, services, type ServiceName } from "@/lib/services";

export async function GET() {
  const names = Object.keys(services) as ServiceName[];

  const results = await Promise.all(
    names.map(async (name) => {
      try {
        const res = await serviceFetch(name, "/health/ready");
        return [name, res.ok ? "up" : "down"] as const;
      } catch {
        return [name, "unreachable"] as const;
      }
    }),
  );

  const allUp = results.every(([, status]) => status === "up");
  return Response.json(
    { status: allUp ? "ok" : "degraded", services: Object.fromEntries(results) },
    { status: allUp ? 200 : 503 },
  );
}
