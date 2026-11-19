import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { Spinner } from "@/components/ui/spinner";
import { getBalance, getOrder } from "@/lib/credits";

import { OrderPanel } from "./order-panel";

export const metadata: Metadata = { title: "Pagamento · Veriditi" };

async function Order({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [order, balance] = await Promise.all([getOrder(id), getBalance()]);
  if (!order) notFound();
  return <OrderPanel initialOrder={order} initialBalance={balance} />;
}

export default function PedidoPage({ params }: PageProps<"/creditos/pedidos/[id]">) {
  return (
    <div className="flex flex-col gap-6">
      <nav aria-label="Etapas da compra">
        <Link href="/creditos" className="text-sm font-bold text-brand underline">
          ← Voltar para créditos
        </Link>
      </nav>
      <h1 className="text-2xl font-extrabold text-brand-strong sm:text-3xl">3. Pagamento</h1>
      <Suspense fallback={<Spinner label="Carregando pedido" />}>
        <Order params={params} />
      </Suspense>
    </div>
  );
}
