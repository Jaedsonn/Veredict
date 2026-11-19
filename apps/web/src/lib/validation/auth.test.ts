import { describe, expect, it } from "vitest";

import { fieldErrorsOf, registerSchema } from "@/lib/validation/auth";

const base = {
  name: "Maria",
  email: "maria@example.com",
  password: "SenhaForte123",
  confirmPassword: "SenhaForte123",
  terms: "on",
};

function errorsOf(values: Record<string, string>) {
  const result = registerSchema.safeParse(values);
  return result.success ? {} : fieldErrorsOf(result.error);
}

describe("registerSchema", () => {
  it("aceita conta comum e normaliza o CPF para dígitos", () => {
    const result = registerSchema.safeParse({ ...base, userType: "common", cpf: "529.982.247-25" });

    expect(result.success && result.data.cpf).toBe("52998224725");
  });

  it("ignora a OAB da conta comum", () => {
    expect(errorsOf({ ...base, userType: "common", cpf: "52998224725", oabNumber: "x" })).toEqual({});
  });

  it("exige tipo de conta e CPF válido", () => {
    expect(errorsOf({ ...base, cpf: "529.982.247-24" })).toEqual({
      userType: "Escolha o tipo de conta.",
      cpf: "CPF inválido.",
    });
  });

  it("exige os três campos da OAB do advogado, junto com os outros erros", () => {
    expect(errorsOf({ ...base, confirmPassword: "outra", userType: "lawyer", cpf: "" })).toEqual({
      confirmPassword: "As senhas não coincidem.",
      cpf: "CPF inválido.",
      oabNumber: "Informe o número da OAB com até 6 dígitos.",
      oabUf: "Escolha a UF da seccional.",
      oabKind: "Escolha o tipo de inscrição.",
    });
  });

  it.each(["0", "000", "1234567", "12a4"])("recusa o número de OAB %j", (oabNumber) => {
    const errors = errorsOf({
      ...base,
      userType: "lawyer",
      cpf: "52998224725",
      oabNumber,
      oabUf: "BA",
      oabKind: "principal",
    });

    expect(errors).toEqual({ oabNumber: "Informe o número da OAB com até 6 dígitos." });
  });

  it("aceita o advogado com OAB completa", () => {
    const values = { oabNumber: "012345", oabUf: "BA", oabKind: "transitoria" };

    expect(errorsOf({ ...base, userType: "lawyer", cpf: "52998224725", ...values })).toEqual({});
  });
});
