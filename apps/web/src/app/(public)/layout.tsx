import Link from "next/link";

import { Logo } from "@/components/brand/logo";

/** Telas de entrada: split-screen com a coluna da marca à esquerda. */
export default function PublicLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex min-h-full flex-1 flex-col md:flex-row">
      <aside className="flex flex-col gap-6 bg-brand px-4 py-6 text-white sm:px-8 md:w-2/5 md:max-w-md md:justify-between md:py-12 lg:px-12">
        <div className="flex flex-col gap-4">
          <Link href="/" className="w-fit rounded-input">
            <Logo tone="light" className="text-3xl md:text-4xl" />
          </Link>
          <p className="hidden max-w-sm text-lg leading-relaxed text-white/90 md:block">
            Coleta, autenticação e preservação de provas digitais com valor probatório.
          </p>
        </div>
        <ul className="hidden flex-col gap-3 text-sm text-white/85 md:flex">
          <li>Registro de auditoria de cada ação</li>
          <li>Verificação de integridade por hash</li>
          <li>Acesso protegido por verificação de e-mail</li>
        </ul>
      </aside>
      <main className="flex flex-1 items-start justify-center bg-background-muted px-4 py-8 sm:px-8 md:items-center md:py-12">
        <div className="w-full max-w-md">{children}</div>
      </main>
    </div>
  );
}
