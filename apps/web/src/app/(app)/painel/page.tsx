import type { Metadata } from "next";
import { Suspense } from "react";

import { Card } from "@/components/ui/card";
import { getCurrentUser } from "@/lib/user";

export const metadata: Metadata = { title: "Painel · Veriditi" };

async function Greeting() {
  const user = await getCurrentUser();
  const first = user.name.trim().split(/\s+/)[0];
  return <>Olá, {first}!</>;
}

function ComingSoon() {
  return (
    <span className="rounded-full bg-tab-active px-3 py-1 text-xs font-bold text-brand-strong">em breve</span>
  );
}

export default function PainelPage() {
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-extrabold text-brand-strong sm:text-3xl">
          <Suspense fallback="Olá!">
            <Greeting />
          </Suspense>
        </h1>
        <p className="text-muted-foreground">Bem-vindo(a) ao Veriditi.</p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card aria-labelledby="creditos-title" className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-2">
            <h2 id="creditos-title" className="text-lg font-extrabold text-brand-strong">
              Créditos
            </h2>
            <ComingSoon />
          </div>
          <p className="label-mono">—% dos créditos utilizados</p>
          <p className="label-mono">—% de armazenamento disponível</p>
          <p className="text-sm text-muted-foreground">
            A compra de pacotes de créditos estará disponível na próxima etapa.
          </p>
        </Card>

        <Card aria-labelledby="provas-title" className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-2">
            <h2 id="provas-title" className="text-lg font-extrabold text-brand-strong">
              Minhas provas
            </h2>
            <ComingSoon />
          </div>
          <div className="flex min-h-24 items-center justify-center rounded-input bg-media/40 p-4 text-center text-sm text-brand-strong">
            Suas capturas e gravações aparecerão aqui.
          </div>
          <button
            type="button"
            disabled
            className="min-h-11 rounded-button bg-brand px-5 text-sm font-bold text-white opacity-60"
          >
            Iniciar uma gravação
          </button>
        </Card>
      </div>
    </div>
  );
}
