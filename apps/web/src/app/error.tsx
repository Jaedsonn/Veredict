"use client";

import AppError from "./(app)/error";

/** Cobre erros fora das páginas (ex.: o layout da área logada não conseguiu carregar o usuário). */
export default function RootError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="flex flex-1 items-center justify-center bg-background-muted px-4 py-10">
      <div className="w-full max-w-md">
        <AppError {...props} />
      </div>
    </main>
  );
}
