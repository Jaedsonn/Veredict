import type { ReactNode } from "react";

import { cn } from "./cn";

type Tone = "error" | "success" | "info";

const TONES: Record<Tone, string> = {
  error: "border-danger bg-red-50 text-danger",
  success: "border-success bg-green-50 text-success",
  info: "border-brand bg-white text-brand-strong",
};

export function Alert({ tone = "info", title, children }: { tone?: Tone; title?: string; children?: ReactNode }) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn("rounded-input border-l-4 px-4 py-3 text-sm", TONES[tone])}
    >
      {title && <p className="font-bold">{title}</p>}
      {children && <div className={title ? "mt-1" : undefined}>{children}</div>}
    </div>
  );
}
