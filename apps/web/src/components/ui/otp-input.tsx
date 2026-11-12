"use client";

import { useRef, useState, type ClipboardEvent, type KeyboardEvent } from "react";

import { cn } from "./cn";

/**
 * Código de N dígitos, um campo por dígito (#13). Reutilizado no MFA (#20).
 * Envia o valor combinado num input oculto com o `name` informado.
 */
export function OtpInput({
  name,
  length = 6,
  invalid,
  disabled,
  describedBy,
  label = "Código de verificação",
}: {
  name: string;
  length?: number;
  invalid?: boolean;
  disabled?: boolean;
  describedBy?: string;
  label?: string;
}) {
  const [digits, setDigits] = useState<string[]>(() => Array(length).fill(""));
  const refs = useRef<Array<HTMLInputElement | null>>([]);

  const focus = (i: number) => refs.current[Math.max(0, Math.min(length - 1, i))]?.focus();

  const fill = (start: number, text: string) => {
    const chars = text.replace(/\D/g, "").slice(0, length - start).split("");
    if (chars.length === 0) return;
    setDigits((prev) => {
      const next = [...prev];
      chars.forEach((c, k) => (next[start + k] = c));
      return next;
    });
    focus(start + chars.length);
  };

  const onChange = (i: number, value: string) => {
    const clean = value.replace(/\D/g, "");
    if (clean.length > 1) return fill(i, clean); // autocomplete do celular entrega tudo de uma vez
    setDigits((prev) => {
      const next = [...prev];
      next[i] = clean;
      return next;
    });
    if (clean) focus(i + 1);
  };

  const onKeyDown = (i: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !digits[i] && i > 0) {
      e.preventDefault();
      setDigits((prev) => {
        const next = [...prev];
        next[i - 1] = "";
        return next;
      });
      focus(i - 1);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      focus(i - 1);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      focus(i + 1);
    }
  };

  const onPaste = (i: number, e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    fill(i, e.clipboardData.getData("text"));
  };

  return (
    <fieldset className="flex flex-col gap-2" aria-describedby={describedBy}>
      <legend className="label-mono mb-2">{label}</legend>
      <div className="flex gap-2 sm:gap-3">
        {digits.map((d, i) => (
          <input
            key={i}
            ref={(el) => {
              refs.current[i] = el;
            }}
            value={d}
            onChange={(e) => onChange(i, e.target.value)}
            onKeyDown={(e) => onKeyDown(i, e)}
            onPaste={(e) => onPaste(i, e)}
            onFocus={(e) => e.target.select()}
            inputMode="numeric"
            pattern="[0-9]*"
            autoComplete={i === 0 ? "one-time-code" : "off"}
            maxLength={length}
            disabled={disabled}
            aria-label={`Dígito ${i + 1} de ${length}`}
            aria-invalid={invalid || undefined}
            className={cn(
              "h-14 w-full min-w-0 max-w-14 rounded-input border-2 bg-white text-center font-mono text-2xl font-bold text-brand-strong",
              "focus:border-focus focus:outline-none",
              invalid ? "border-danger" : "border-transparent",
            )}
          />
        ))}
      </div>
      <input type="hidden" name={name} value={digits.join("")} />
    </fieldset>
  );
}
