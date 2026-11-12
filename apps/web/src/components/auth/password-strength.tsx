import { passwordRules } from "@/lib/validation/auth";

/** Indicador de força com as mesmas regras da API (#7). */
export function PasswordStrength({ value }: { value: string }) {
  const passed = passwordRules.filter((r) => r.test(value)).length;
  const extra = value.length >= 14 && /[^\p{L}\d]/u.test(value) ? 1 : 0;
  const score = passed + extra; // 0..4
  const labels = ["Muito fraca", "Fraca", "Razoável", "Boa", "Forte"];
  const colors = ["bg-danger", "bg-danger", "bg-amber-600", "bg-success", "bg-success"];

  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-1" aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <span key={i} className={`h-1.5 flex-1 rounded-full ${i < score ? colors[score] : "bg-white"}`} />
        ))}
      </div>
      <p className="text-sm text-muted-foreground" aria-live="polite">
        Força da senha: <strong className="text-foreground">{value ? labels[score] : "—"}</strong>
      </p>
      <ul className="flex flex-col gap-0.5 text-sm">
        {passwordRules.map((r) => {
          const ok = r.test(value);
          return (
            <li key={r.id} className={ok ? "text-success" : "text-muted-foreground"}>
              <span aria-hidden="true">{ok ? "✓" : "○"}</span> {r.label}
              <span className="sr-only">{ok ? " (atendido)" : " (pendente)"}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
