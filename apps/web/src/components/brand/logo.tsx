import { cn } from "@/components/ui/cn";

export function Logo({ className, tone = "dark" }: { className?: string; tone?: "dark" | "light" }) {
  return (
    <span
      className={cn(
        "text-2xl font-extrabold tracking-tight",
        tone === "light" ? "text-white" : "text-brand",
        className,
      )}
    >
      Veriditi
    </span>
  );
}
