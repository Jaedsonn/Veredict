import type { Metadata } from "next";
import { Suspense } from "react";

import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";

import { VerifyEmailForm } from "./verify-form";

export const metadata: Metadata = { title: "Verificar e-mail · Veriditi" };

export default function VerificarEmailPage() {
  return (
    <Card>
      {/* O formulário lê ?email= da URL: fica atrás de Suspense (Cache Components). */}
      <Suspense fallback={<Spinner />}>
        <VerifyEmailForm />
      </Suspense>
    </Card>
  );
}
