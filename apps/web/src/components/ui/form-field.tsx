import { cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";

type ControlProps = {
  id?: string;
  invalid?: boolean;
  "aria-describedby"?: string;
};

/**
 * Label + controle + dica + erro. Liga o erro ao campo com `aria-describedby`
 * para leitores de tela (#12).
 */
export function FormField({
  id,
  label,
  error,
  hint,
  children,
}: {
  id: string;
  label: ReactNode;
  error?: string;
  hint?: ReactNode;
  children: ReactElement<ControlProps>;
}) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  const control = isValidElement(children)
    ? cloneElement(children, { id, invalid: Boolean(error), "aria-describedby": describedBy })
    : children;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="label-mono">
        {label}
      </label>
      {control}
      {hint && (
        <div id={hintId} className="text-sm text-muted-foreground">
          {hint}
        </div>
      )}
      {error && (
        <p id={errorId} className="text-sm font-medium text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
