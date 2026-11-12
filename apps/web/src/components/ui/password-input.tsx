"use client";

import { useState } from "react";

import { inputClasses, type InputProps } from "./input";

export function PasswordInput({ invalid, className, ...rest }: Omit<InputProps, "type">) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <input
        type={visible ? "text" : "password"}
        aria-invalid={invalid || undefined}
        className={inputClasses(invalid, `pr-20 ${className ?? ""}`)}
        {...rest}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-pressed={visible}
        aria-controls={rest.id}
        className="absolute inset-y-1 right-1 rounded-input px-3 text-sm font-bold text-brand hover:bg-brand/10"
      >
        {visible ? "Ocultar" : "Mostrar"}
        <span className="sr-only"> senha</span>
      </button>
    </div>
  );
}
