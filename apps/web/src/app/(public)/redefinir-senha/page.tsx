import type { Metadata } from "next";
import { Suspense } from "react";

import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";

import { ResetPasswordForm } from "./reset-form";

// Reforça o header do next.config.ts: o token da URL não sai no Referer.
export const metadata: Metadata = {
  title: "Redefinir senha · Veriditi",
  referrer: "no-referrer",
  robots: { index: false, follow: false },
};

export default function RedefinirSenhaPage() {
  return (
    <Card>
      {/* O formulário lê ?token= da URL: fica atrás de Suspense (Cache Components). */}
      <Suspense fallback={<Spinner />}>
        <ResetPasswordForm />
      </Suspense>
    </Card>
  );
}
