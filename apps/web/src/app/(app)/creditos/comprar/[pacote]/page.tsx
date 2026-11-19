import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { Card, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { getPackages } from "@/lib/credits";
import { creditsLabel, formatBRL } from "@/lib/money";
import { getCurrentUser } from "@/lib/user";

import { BillingForm } from "./billing-form";

export const metadata: Metadata = { title: "Comprar créditos · Veriditi" };

async function Checkout({ params }: { params: Promise<{ pacote: string }> }) {
  const { pacote } = await params;
  const [packages, user] = await Promise.all([getPackages(), getCurrentUser()]);
  const selected = packages.find((p) => p.code === pacote);
  if (!selected) notFound();

  return (
    <>
      <Card aria-labelledby="resumo-title" className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h2 id="resumo-title" className="label-mono">
            Pacote escolhido:
          </h2>
          <p className="text-xl font-extrabold text-brand-strong">
            {selected.name} · {creditsLabel(selected.credits)}
          </p>
          <p className="text-sm text-muted-foreground">{formatBRL(selected.unit_price_cents)} por crédito</p>
        </div>
        <p className="text-3xl font-extrabold text-brand-strong">{formatBRL(selected.price_cents)}</p>
      </Card>

      <Card className="flex flex-col gap-5">
        <div className="flex flex-col gap-1">
          <CardTitle>2. Dados de faturamento</CardTitle>
          <p className="text-sm text-muted-foreground">
            Usados na cobrança. O CPF vai só para o pagamento e fica guardado apenas mascarado.
          </p>
        </div>
        <BillingForm
          packageCode={selected.code}
          idempotencyKey={crypto.randomUUID()}
          defaults={{ name: user.name, email: user.email }}
        />
      </Card>
    </>
  );
}

export default function ComprarPage({ params }: PageProps<"/creditos/comprar/[pacote]">) {
  return (
    <div className="flex flex-col gap-6">
      <nav aria-label="Etapas da compra">
        <Link href="/creditos" className="text-sm font-bold text-brand underline">
          ← Trocar de pacote
        </Link>
      </nav>
      <h1 className="text-2xl font-extrabold text-brand-strong sm:text-3xl">Comprar créditos</h1>
      <Suspense fallback={<Spinner label="Carregando pacote" />}>
        <Checkout params={params} />
      </Suspense>
    </div>
  );
}
