"use client";

import { useActionState, useState } from "react";

import { PasswordStrength } from "@/components/auth/password-strength";
import { useClientValidation } from "@/components/forms/use-client-validation";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { PasswordInput } from "@/components/ui/password-input";
import { initialFormState } from "@/lib/form-state";
import { passwordChangeSchema } from "@/lib/validation/auth";

import { changePasswordAction } from "./actions";

export function PasswordForm() {
  const [state, formAction, pending] = useActionState(changePasswordAction, initialFormState);
  const { errors, onSubmit } = useClientValidation(passwordChangeSchema, state.fieldErrors);
  const [newPassword, setNewPassword] = useState("");
  const [handled, setHandled] = useState(state);
  if (state !== handled) {
    setHandled(state);
    if (state.status === "success") setNewPassword("");
  }

  return (
    <form action={formAction} onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {state.message && <Alert tone={state.status === "success" ? "success" : "error"}>{state.message}</Alert>}
      <FormField id="currentPassword" label="Senha atual:" error={errors.currentPassword}>
        <PasswordInput name="currentPassword" autoComplete="current-password" required />
      </FormField>
      <FormField
        id="newPassword"
        label="Nova senha:"
        error={errors.newPassword}
        hint={<PasswordStrength value={newPassword} />}
      >
        <PasswordInput
          name="newPassword"
          autoComplete="new-password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          required
        />
      </FormField>
      <FormField id="confirmNewPassword" label="Confirmar nova senha:" error={errors.confirmPassword}>
        <PasswordInput name="confirmPassword" autoComplete="new-password" required />
      </FormField>
      <div>
        <Button type="submit" pending={pending}>
          Alterar senha
        </Button>
      </div>
    </form>
  );
}
