import { GATEWAY_URL } from "@/lib/config";

/** Health da web: consulta o health agregado do gateway (#11/#12). */
export async function GET() {
  try {
    const res = await fetch(new URL("/health/ready", GATEWAY_URL), {
      signal: AbortSignal.timeout(3_000),
      cache: "no-store",
    });
    const gateway: unknown = await res.json().catch(() => null);
    return Response.json(
      { status: res.ok ? "ok" : "degraded", gateway },
      { status: res.ok ? 200 : 503 },
    );
  } catch {
    return Response.json({ status: "degraded", gateway: "unreachable" }, { status: 503 });
  }
}
