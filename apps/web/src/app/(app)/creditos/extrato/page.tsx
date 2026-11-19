import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { buttonClasses } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { getStatement, type LedgerEntry } from "@/lib/credits";
import { creditsLabel } from "@/lib/money";

export const metadata: Metadata = { title: "Extrato de créditos · Veriditi" };

const dateTime = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
  timeStyle: "short",
  timeZone: "America/Sao_Paulo",
});

const REASONS: Record<LedgerEntry["reason"], string> = {
  purchase: "Compra de créditos",
  capture: "Registro de ocorrência",
  refund: "Estorno",
  adjustment: "Ajuste",
};

function signed(n: number): string {
  return n > 0 ? `+${n}` : String(n);
}

async function Statement() {
  const { balance, entries } = await getStatement();
  return (
    <Card className="flex flex-col gap-5">
      <p className="text-xl font-extrabold text-brand-strong">Saldo: {creditsLabel(balance)}</p>
      {entries.length === 0 ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-muted-foreground">Nenhum movimento ainda.</p>
          <Link href="/creditos" className={buttonClasses("primary")}>
            Comprar créditos
          </Link>
        </div>
      ) : (
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Movimentos da carteira de créditos, do mais recente ao mais antigo</caption>
          <thead className="hidden sm:table-header-group">
            <tr className="border-b border-brand/20">
              <th scope="col" className="py-2 pr-4 label-mono">Data</th>
              <th scope="col" className="py-2 pr-4 label-mono">Descrição</th>
              <th scope="col" className="py-2 pr-4 text-right label-mono">Créditos</th>
              <th scope="col" className="py-2 text-right label-mono">Saldo após</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id} className="grid grid-cols-2 gap-1 border-b border-brand/10 py-3 sm:table-row">
                <td className="sm:py-3 sm:pr-4">{dateTime.format(new Date(e.created_at))}</td>
                <td className="text-right font-medium sm:py-3 sm:pr-4 sm:text-left">{REASONS[e.reason]}</td>
                <td
                  className={`font-bold sm:py-3 sm:pr-4 sm:text-right ${e.delta > 0 ? "text-success" : "text-danger"}`}
                >
                  <span className="sm:hidden">Créditos: </span>
                  {signed(e.delta)}
                </td>
                <td className="text-right sm:py-3">
                  <span className="sm:hidden">Saldo após: </span>
                  {e.balance_after}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

export default function ExtratoPage() {
  return (
    <div className="flex flex-col gap-6">
      <nav aria-label="Créditos">
        <Link href="/creditos" className="text-sm font-bold text-brand underline">
          ← Voltar para créditos
        </Link>
      </nav>
      <h1 className="text-2xl font-extrabold text-brand-strong sm:text-3xl">Extrato de créditos</h1>
      <Suspense fallback={<Spinner label="Carregando extrato" />}>
        <Statement />
      </Suspense>
    </div>
  );
}
