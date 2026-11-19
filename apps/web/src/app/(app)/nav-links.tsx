"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/components/ui/cn";

const LINKS = [
  { href: "/painel", label: "Painel" },
  { href: null, label: "Minhas provas" }, // Sprint 2 (#32)
  { href: "/creditos", label: "Créditos" },
  { href: "/perfil", label: "Perfil" },
] as const;

const itemBase = "flex min-h-11 shrink-0 items-center rounded-button px-4 text-sm font-bold whitespace-nowrap";

/** Lista do menu; sem hook, serve também de fallback enquanto o caminho não é conhecido. */
export function NavList({ pathname }: { pathname?: string }) {
  return (
    <ul className="flex gap-1 md:flex-col">
      {LINKS.map((l) => {
        if (!l.href) {
          return (
            <li key={l.label}>
              <span aria-disabled="true" className={cn(itemBase, "cursor-not-allowed gap-2 text-white/60")}>
                {l.label}
                <span className="rounded-full bg-white/15 px-2 py-0.5 text-xs font-medium">em breve</span>
              </span>
            </li>
          );
        }
        const active = pathname !== undefined && (pathname === l.href || pathname.startsWith(`${l.href}/`));
        return (
          <li key={l.href}>
            <Link
              href={l.href}
              aria-current={active ? "page" : undefined}
              className={cn(itemBase, active ? "bg-brand-strong text-white" : "text-white/85 hover:bg-white/10")}
            >
              {l.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Destaca o item da página atual. Fica dentro de `<Suspense>` no layout: em rotas com
 * parâmetro (`/creditos/pedidos/[id]`) o caminho só é conhecido na requisição.
 */
export function NavLinks() {
  return <NavList pathname={usePathname()} />;
}
