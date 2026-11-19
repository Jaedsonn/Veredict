import type { Metadata } from "next";
import Link from "next/link";

import { Card, CardTitle } from "@/components/ui/card";

import { ForgotPasswordForm } from "./forgot-form";

export const metadata: Metadata = { title: "Esqueci minha senha · Veriditi" };

export default function EsqueciSenhaPage() {
  return (
    <Card>
      <div className="mb-6 flex flex-col gap-1">
        <CardTitle as="h1">Esqueci minha senha</CardTitle>
        <p className="text-sm text-muted-foreground">
          Informe o e-mail da sua conta e enviaremos um link para criar uma nova senha. Lembrou?{" "}
          <Link href="/entrar" className="font-bold text-brand underline">
            Entrar
          </Link>
        </p>
      </div>
      <ForgotPasswordForm />
    </Card>
  );
}
