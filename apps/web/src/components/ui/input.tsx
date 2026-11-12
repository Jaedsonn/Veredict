import type { InputHTMLAttributes } from "react";

import { cn } from "./cn";

export type InputProps = InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean };

export function inputClasses(invalid?: boolean, className?: string) {
  return cn(
    "block min-h-11 w-full rounded-input border-2 bg-white px-3 text-base text-foreground",
    "placeholder:text-muted-foreground/70 focus:border-focus focus:outline-none",
    "disabled:cursor-not-allowed disabled:bg-surface-strong",
    invalid ? "border-danger" : "border-transparent",
    className,
  );
}

export function Input({ invalid, className, ...rest }: InputProps) {
  return <input aria-invalid={invalid || undefined} className={inputClasses(invalid, className)} {...rest} />;
}
