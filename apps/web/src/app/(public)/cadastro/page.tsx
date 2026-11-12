import type { Metadata } from "next";
import Link from "next/link";

import { Card, CardTitle } from "@/components/ui/card";

import { RegisterForm } from "./register-form";

export const metadata: Metadata = { title: "Criar conta · Veriditi" };

export default function CadastroPage() {
  return (
    <Card>
      <div className="mb-6 flex flex-col gap-1">
        <CardTitle as="h1">Criar conta</CardTitle>
        <p className="text-sm text-muted-foreground">
          Já tem conta?{" "}
          <Link href="/entrar" className="font-bold text-brand underline">
            Entrar
          </Link>
        </p>
      </div>
      <RegisterForm />
    </Card>
  );
}
