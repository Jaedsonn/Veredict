import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Card, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Entrar · Veriditi" };

export default function EntrarPage() {
  return (
    <Card>
      <div className="mb-6 flex flex-col gap-1">
        <CardTitle as="h1">Entrar</CardTitle>
        <p className="text-sm text-muted-foreground">
          Ainda não tem conta?{" "}
          <Link href="/cadastro" className="font-bold text-brand underline">
            Cadastre-se
          </Link>
        </p>
      </div>
      <Suspense fallback={<Spinner />}>
        <LoginForm />
      </Suspense>
    </Card>
  );
}
