import type { SelectHTMLAttributes } from "react";

import { inputClasses } from "./input";

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean };

/** `<select>` nativo com o visual do `Input`, para o `FormField` ligar label e erro. */
export function Select({ invalid, className, ...rest }: SelectProps) {
  return <select aria-invalid={invalid || undefined} className={inputClasses(invalid, className)} {...rest} />;
}
