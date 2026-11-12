import Link from "next/link";
import { Suspense } from "react";

import { Logo } from "@/components/brand/logo";
import { Spinner } from "@/components/ui/spinner";

import { NavLinks } from "./nav-links";
import { UserMenu } from "./user-menu";

/** Área autenticada: sidebar azul-marinho (no celular vira barra no topo). */
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex min-h-full flex-1 flex-col md:flex-row md:bg-brand">
      <aside className="flex flex-col gap-4 bg-brand px-4 py-4 text-white md:sticky md:top-0 md:h-dvh md:w-64 md:shrink-0 md:justify-between md:px-5 md:py-8">
        <div className="flex flex-col gap-4 md:gap-8">
          <div className="flex items-center justify-between gap-3">
            <Link href="/painel" className="rounded-input">
              <Logo tone="light" />
            </Link>
            <div className="md:hidden">
              <Suspense fallback={<Spinner className="text-white" />}>
                <UserMenu />
              </Suspense>
            </div>
          </div>
          <nav aria-label="Navegação principal" className="-mx-1 overflow-x-auto px-1 md:mx-0 md:overflow-visible md:px-0">
            <NavLinks />
          </nav>
        </div>
        <div className="hidden md:block">
          <Suspense fallback={<Spinner className="text-white" />}>
            <UserMenu />
          </Suspense>
        </div>
      </aside>
      <main className="flex-1 bg-background-muted px-4 py-6 sm:px-8 md:py-10">
        <div className="mx-auto w-full max-w-4xl">{children}</div>
      </main>
    </div>
  );
}
