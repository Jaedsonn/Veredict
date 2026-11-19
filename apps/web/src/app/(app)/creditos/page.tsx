import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { buttonClasses } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/components/ui/cn";
import { Spinner } from "@/components/ui/spinner";
import { getBalance, getPackages } from "@/lib/credits";
import { creditsLabel, formatBRL } from "@/lib/money";

export const metadata: Metadata = { title: "Créditos · Veriditi" };

async function Balance() {
  const balance = await getBalance();
  return (
    <Card aria-labelledby="saldo-title" className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex flex-col gap-1">
        <h2 id="saldo-title" className="label-mono">
          Seu saldo:
        </h2>
        <p className="text-3xl font-extrabold text-brand-strong">
          {balance === null ? "indisponível" : creditsLabel(balance)}
        </p>
      </div>
      <Link href="/creditos/extrato" className={buttonClasses("secondary")}>
        Ver extrato
      </Link>
    </Card>
  );
}

async function Packages() {
  const packages = await getPackages();
  return (
    <ul className="grid gap-4 md:grid-cols-3">
      {packages.map((p) => (
        <li key={p.code}>
          <Card
            aria-labelledby={`pacote-${p.code}`}
            className={cn("flex h-full flex-col gap-4", p.highlight && "ring-2 ring-brand")}
          >
            <div className="flex items-center justify-between gap-2">
              <h3 id={`pacote-${p.code}`} className="text-xl font-extrabold text-brand-strong">
                {p.name}
              </h3>
              {p.highlight && (
                <span className="rounded-full bg-brand px-3 py-1 text-xs font-bold text-white">mais escolhido</span>
              )}
            </div>
            <dl className="flex flex-col gap-1">
              <dt className="sr-only">Créditos</dt>
              <dd className="text-lg font-bold">{creditsLabel(p.credits)}</dd>
              <dt className="sr-only">Preço</dt>
              <dd className="text-3xl font-extrabold text-brand-strong">{formatBRL(p.price_cents)}</dd>
              <dt className="sr-only">Valor por crédito</dt>
              <dd className="text-sm text-muted-foreground">{formatBRL(p.unit_price_cents)} por crédito</dd>
            </dl>
            <p className="flex-1 text-sm">{p.benefits}</p>
            <Link
              href={`/creditos/comprar/${p.code}`}
              className={buttonClasses(p.highlight ? "primary" : "secondary", true)}
              aria-label={`Comprar o pacote ${p.name}`}
            >
              Comprar
            </Link>
          </Card>
        </li>
      ))}
    </ul>
  );
}

export default function CreditosPage() {
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-extrabold text-brand-strong sm:text-3xl">Créditos</h1>
        <p className="text-muted-foreground">
          Cada registro de ocorrência usa créditos. Escolha um pacote, informe os dados de faturamento e pague
          com PIX.
        </p>
      </header>
      <Suspense fallback={<Spinner label="Carregando saldo" />}>
        <Balance />
      </Suspense>
      <section aria-labelledby="pacotes-title" className="flex flex-col gap-4">
        <h2 id="pacotes-title" className="text-xl font-extrabold text-brand-strong">
          1. Escolha o pacote
        </h2>
        <Suspense fallback={<Spinner label="Carregando pacotes" />}>
          <Packages />
        </Suspense>
      </section>
    </div>
  );
}
