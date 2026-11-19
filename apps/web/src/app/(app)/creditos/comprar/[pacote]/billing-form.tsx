"use client";

import { useActionState, useState } from "react";

import { useClientValidation } from "@/components/forms/use-client-validation";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { initialFormState } from "@/lib/form-state";
import { UFS, billingSchema, formatCepInput, formatPhoneInput } from "@/lib/validation/billing";
import { formatCpfInput } from "@/lib/validation/cpf";

import { createOrderAction } from "../../actions";

type Props = {
  packageCode: string;
  idempotencyKey: string;
  defaults: { name: string; email: string };
};

export function BillingForm({ packageCode, idempotencyKey, defaults }: Props) {
  const [state, formAction, pending] = useActionState(createOrderAction, initialFormState);
  const { errors, onSubmit } = useClientValidation(billingSchema, state.fieldErrors);
  const v = state.values ?? {};
  // Controlados por causa das máscaras; o CPF não volta do servidor (publicValues)
  const [cpf, setCpf] = useState("");
  const [phone, setPhone] = useState(v.phone ?? "");
  const [cep, setCep] = useState(v.cep ?? "");
  const [uf, setUf] = useState(v.state ?? "");
  // Chave nova só quando o provedor falhou: um clique duplo reaproveita a mesma
  const key = typeof state.meta?.idempotencyKey === "string" ? state.meta.idempotencyKey : idempotencyKey;

  return (
    <form action={formAction} onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      {state.message && <Alert tone="error">{state.message}</Alert>}
      <input type="hidden" name="packageCode" value={packageCode} />
      <input type="hidden" name="idempotencyKey" value={key} />

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <FormField id="name" label="Nome completo:" error={errors.name}>
            <Input name="name" autoComplete="name" defaultValue={v.name ?? defaults.name} maxLength={120} required />
          </FormField>
        </div>
        <FormField id="email" label="E-mail:" error={errors.email}>
          <Input name="email" type="email" autoComplete="email" defaultValue={v.email ?? defaults.email} required />
        </FormField>
        <FormField id="phone" label="Telefone:" error={errors.phone}>
          <Input
            name="phone"
            type="tel"
            inputMode="tel"
            autoComplete="tel-national"
            placeholder="(00) 00000-0000"
            maxLength={15}
            value={phone}
            onChange={(e) => setPhone(formatPhoneInput(e.target.value))}
            required
          />
        </FormField>
        <FormField id="cpf" label="CPF:" error={errors.cpf}>
          <Input
            name="cpf"
            inputMode="numeric"
            autoComplete="off"
            placeholder="000.000.000-00"
            maxLength={14}
            value={cpf}
            onChange={(e) => setCpf(formatCpfInput(e.target.value))}
            required
          />
        </FormField>
        <FormField id="cep" label="CEP:" error={errors.cep}>
          <Input
            name="cep"
            inputMode="numeric"
            autoComplete="postal-code"
            placeholder="00000-000"
            maxLength={9}
            value={cep}
            onChange={(e) => setCep(formatCepInput(e.target.value))}
            required
          />
        </FormField>
        <div className="sm:col-span-2">
          <FormField id="street" label="Endereço:" error={errors.street}>
            <Input name="street" autoComplete="address-line1" defaultValue={v.street} maxLength={120} required />
          </FormField>
        </div>
        <FormField id="number" label="Número:" error={errors.number}>
          <Input name="number" autoComplete="off" defaultValue={v.number} maxLength={10} required />
        </FormField>
        <FormField id="complement" label="Complemento (opcional):" error={errors.complement}>
          <Input name="complement" autoComplete="address-line2" defaultValue={v.complement} maxLength={60} />
        </FormField>
        <FormField id="district" label="Bairro:" error={errors.district}>
          <Input name="district" autoComplete="address-level3" defaultValue={v.district} maxLength={60} required />
        </FormField>
        <FormField id="city" label="Cidade:" error={errors.city}>
          <Input name="city" autoComplete="address-level2" defaultValue={v.city} maxLength={60} required />
        </FormField>
        <FormField id="state" label="Estado:" error={errors.state}>
          <Select name="state" autoComplete="address-level1" value={uf} onChange={(e) => setUf(e.target.value)} required>
            <option value="" disabled>
              UF
            </option>
            {UFS.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </Select>
        </FormField>
      </div>

      <Button type="submit" pending={pending} fullWidth>
        Continuar para o pagamento
      </Button>
    </form>
  );
}
