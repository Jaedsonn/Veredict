import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "./cn";

export function Card({ className, ...rest }: HTMLAttributes<HTMLElement>) {
  return <section className={cn("rounded-card bg-surface p-6 sm:p-8", className)} {...rest} />;
}

export function CardTitle({ children, as: Tag = "h2" }: { children: ReactNode; as?: "h1" | "h2" | "h3" }) {
  return <Tag className="text-xl font-extrabold text-brand-strong">{children}</Tag>;
}
