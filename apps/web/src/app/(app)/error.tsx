"use client";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export default function AppError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="flex flex-col items-start gap-4">
      <Alert tone="error" title="Não foi possível carregar esta página.">
        O serviço pode estar indisponível no momento. Tente novamente em instantes.
      </Alert>
      <Button onClick={reset}>Tentar novamente</Button>
    </div>
  );
}
