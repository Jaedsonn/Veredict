import { getCurrentUser } from "@/lib/user";

import { logoutAction } from "./actions";

function initials(name: string) {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "")).toUpperCase();
}

/** Nome do usuário + Sair. Lê a sessão, então fica atrás de Suspense no layout. */
export async function UserMenu() {
  const user = await getCurrentUser();
  return (
    <div className="flex items-center gap-3 md:flex-col md:items-stretch">
      <div className="flex min-w-0 items-center gap-3">
        <span
          aria-hidden="true"
          className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand-strong text-sm font-extrabold text-white"
        >
          {initials(user.name)}
        </span>
        <span className="hidden min-w-0 md:block">
          <span className="block truncate text-sm font-bold text-white">{user.name}</span>
          <span className="block truncate text-xs text-white/75">{user.email}</span>
        </span>
        <span className="sr-only md:hidden">{user.name}</span>
      </div>
      <form action={logoutAction}>
        <button
          type="submit"
          className="min-h-11 w-full rounded-button px-4 text-sm font-bold text-white ring-1 ring-white/40 hover:bg-white/10"
        >
          Sair
        </button>
      </form>
    </div>
  );
}
