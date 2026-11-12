"use client";

import { useActionState } from "react";

import { useClientValidation } from "@/components/forms/use-client-validation";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { initialFormState } from "@/lib/form-state";
import { profileSchema } from "@/lib/validation/auth";

import { updateProfileAction } from "./actions";

export function ProfileForm({ name }: { name: string }) {
  const [state, formAction, pending] = useActionState(updateProfileAction, initialFormState);
  const { errors, onSubmit } = useClientValidation(profileSchema, state.fieldErrors);

  return (
    <form action={formAction} onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {state.message && <Alert tone={state.status === "success" ? "success" : "error"}>{state.message}</Alert>}
      <FormField id="name" label="Nome completo:" error={errors.name}>
        <Input name="name" autoComplete="name" defaultValue={state.values?.name ?? name} maxLength={120} required />
      </FormField>
      <div>
        <Button type="submit" pending={pending}>
          Salvar nome
        </Button>
      </div>
    </form>
  );
}
