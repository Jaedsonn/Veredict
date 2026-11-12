import type { Metadata } from "next";
import { Suspense } from "react";

import { Card, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { getCurrentUser } from "@/lib/user";

import { PasswordForm } from "./password-form";
import { ProfileForm } from "./profile-form";

export const metadata: Metadata = { title: "Perfil · Veriditi" };

const dateFormat = new Intl.DateTimeFormat("pt-BR", { dateStyle: "long", timeZone: "America/Sao_Paulo" });

async function ProfileDetails() {
  const user = await getCurrentUser();
  return (
    <div className="flex flex-col gap-6">
      <Card className="flex flex-col gap-5">
        <CardTitle>Dados da conta</CardTitle>
        <dl className="grid gap-4 sm:grid-cols-2">
          <div className="flex min-w-0 flex-col gap-1">
            <dt className="label-mono">E-mail:</dt>
            <dd className="break-words font-medium">{user.email}</dd>
          </div>
          <div className="flex flex-col gap-1">
            <dt className="label-mono">Cadastro em:</dt>
            <dd className="font-medium">{dateFormat.format(new Date(user.created_at))}</dd>
          </div>
        </dl>
        <ProfileForm name={user.name} />
      </Card>

      <Card className="flex flex-col gap-5">
        <div className="flex flex-col gap-1">
          <CardTitle>Alterar senha</CardTitle>
          <p className="text-sm text-muted-foreground">
            Ao alterar a senha, as outras sessões abertas são encerradas.
          </p>
        </div>
        <PasswordForm />
      </Card>
    </div>
  );
}

export default function PerfilPage() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold text-brand-strong sm:text-3xl">Perfil</h1>
      <Suspense fallback={<Spinner label="Carregando perfil" />}>
        <ProfileDetails />
      </Suspense>
    </div>
  );
}
