"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";

import { Alert } from "@/components/ui/alert";
import { Button, buttonClasses } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import type { Order } from "@/lib/credits";
import { creditsLabel, formatBRL } from "@/lib/money";

import { pollOrderAction, simulatePaymentAction } from "../../actions";

const POLL_MS = 3000;

function remaining(expiresAt: string, now: number): string {
  const seconds = Math.max(0, Math.floor((Date.parse(expiresAt) - now) / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

export function OrderPanel({ initialOrder, initialBalance }: { initialOrder: Order; initialBalance: number | null }) {
  const [order, setOrder] = useState(initialOrder);
  const [balance, setBalance] = useState(initialBalance);
  const [now, setNow] = useState(() => Date.now());
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [paying, startPaying] = useTransition();
  const pending = order.status === "pending";

  // Relógio da validade e polling do status enquanto o PIX espera pagamento
  useEffect(() => {
    if (!pending) return;
    const tick = setInterval(() => setNow(Date.now()), 1000);
    const poll = setInterval(async () => {
      const res = await pollOrderAction(order.id);
      if (res.ok) setOrder(res.order);
    }, POLL_MS);
    return () => {
      clearInterval(tick);
      clearInterval(poll);
    };
  }, [pending, order.id]);

  async function copy() {
    if (!order.pix_copy_paste) return;
    try {
      await navigator.clipboard.writeText(order.pix_copy_paste);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setError("Não foi possível copiar. Selecione o código e copie manualmente.");
    }
  }

  function simulate() {
    setError(null);
    startPaying(async () => {
      const res = await simulatePaymentAction(order.id);
      if (res.ok) {
        setOrder(res.order);
        setBalance(res.balance);
      } else {
        setError(res.message);
        const poll = await pollOrderAction(order.id);
        if (poll.ok) setOrder(poll.order);
      }
    });
  }

  const summary = (
    <p className="text-muted-foreground">
      Pacote <strong className="text-foreground">{order.package.name}</strong> · {creditsLabel(order.credits)} ·{" "}
      <strong className="text-foreground">{formatBRL(order.amount_cents)}</strong>
    </p>
  );

  if (order.status === "paid") {
    return (
      <Card className="flex flex-col gap-5">
        <Alert tone="success" title="Pagamento confirmado!">
          {creditsLabel(order.credits)} foram adicionados à sua carteira.
        </Alert>
        {summary}
        <p className="text-2xl font-extrabold text-brand-strong" aria-live="polite">
          Saldo atual: {balance === null ? "indisponível" : creditsLabel(balance)}
        </p>
        <div className="flex flex-wrap gap-3">
          <Link href="/painel" className={buttonClasses("primary")}>
            Ir para o painel
          </Link>
          <Link href="/creditos/extrato" className={buttonClasses("secondary")}>
            Ver extrato
          </Link>
        </div>
      </Card>
    );
  }

  if (order.status !== "pending") {
    const expired = order.status === "expired";
    return (
      <Card className="flex flex-col gap-5">
        <Alert tone="error" title={expired ? "Este PIX expirou." : "Não foi possível iniciar o pagamento."}>
          {expired ? "O prazo de pagamento terminou e nada foi cobrado." : "Nada foi cobrado. Tente de novo."}
        </Alert>
        {summary}
        <Link href={`/creditos/comprar/${order.package.code}`} className={buttonClasses("primary")}>
          Gerar novo PIX
        </Link>
      </Card>
    );
  }

  return (
    <Card className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <CardTitle>Pague com PIX</CardTitle>
        {summary}
      </div>
      {order.provider === "sandbox" && (
        <Alert tone="info" title="Ambiente de demonstração">
          O PIX é simulado e nenhum valor é cobrado. Use o botão &quot;Simular pagamento&quot; para confirmar.
        </Alert>
      )}
      {error && <Alert tone="error">{error}</Alert>}

      <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-start">
        {order.pix_qr_svg && (
          // eslint-disable-next-line @next/next/no-img-element -- SVG gerado pelo serviço, em data URI
          <img
            src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(order.pix_qr_svg)}`}
            alt="QR Code do PIX"
            width={208}
            height={208}
            className="size-52 shrink-0 rounded-input bg-white p-2"
          />
        )}
        <div className="flex w-full min-w-0 flex-col gap-3">
          <label htmlFor="pix-code" className="label-mono">
            PIX copia e cola:
          </label>
          <textarea
            id="pix-code"
            readOnly
            rows={4}
            value={order.pix_copy_paste ?? ""}
            className="w-full resize-none break-all rounded-input border-2 border-brand/20 bg-white p-3 font-mono text-xs"
            onFocus={(e) => e.currentTarget.select()}
          />
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="secondary" onClick={copy}>
              {copied ? "Copiado!" : "Copiar código PIX"}
            </Button>
            <span className="sr-only" aria-live="polite">
              {copied ? "Código PIX copiado." : ""}
            </span>
            <p className="text-sm text-muted-foreground">
              Expira em <span className="font-mono font-bold">{remaining(order.expires_at, now)}</span>
            </p>
          </div>
        </div>
      </div>

      <p className="text-sm text-muted-foreground" aria-live="polite">
        Aguardando o pagamento. Esta tela atualiza sozinha.
      </p>
      {order.provider === "sandbox" && (
        <Button onClick={simulate} pending={paying} fullWidth>
          Simular pagamento
        </Button>
      )}
    </Card>
  );
}
