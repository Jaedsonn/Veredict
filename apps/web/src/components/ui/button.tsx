import type { ButtonHTMLAttributes } from "react";

import { cn } from "./cn";
import { Spinner } from "./spinner";

type Variant = "primary" | "secondary" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand text-brand-foreground hover:bg-brand-strong",
  secondary: "bg-white text-brand-strong ring-1 ring-brand/30 hover:bg-background-muted",
  ghost: "text-brand hover:bg-brand/10",
};

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  /** Mostra spinner e desabilita (evita envio duplo). */
  pending?: boolean;
  fullWidth?: boolean;
};

export function buttonClasses(variant: Variant = "primary", fullWidth = false, className?: string) {
  return cn(
    "inline-flex min-h-11 items-center justify-center gap-2 rounded-button px-5 text-sm font-bold transition-colors",
    "disabled:cursor-not-allowed disabled:opacity-60",
    VARIANTS[variant],
    fullWidth && "w-full",
    className,
  );
}

export function Button({
  variant = "primary",
  pending = false,
  fullWidth = false,
  className,
  disabled,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={buttonClasses(variant, fullWidth, className)}
      disabled={disabled || pending}
      aria-busy={pending || undefined}
      {...rest}
    >
      {pending && <Spinner label="Enviando" />}
      {children}
    </button>
  );
}
