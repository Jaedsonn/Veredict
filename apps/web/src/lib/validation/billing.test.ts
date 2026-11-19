import { describe, expect, it } from "vitest";

import { fieldErrorsOf } from "@/lib/validation/auth";
import {
  billingSchema,
  cepDigits,
  formatCepInput,
  formatPhoneInput,
  phoneDigits,
} from "@/lib/validation/billing";

// Os mesmos casos de services/payment/tests/test_domain.py: web e serviço não divergem
const valid = {
  name: " Ana Maria Souza ",
  email: "Ana@Example.com",
  phone: "(71) 99876-5432",
  cpf: "529.982.247-25",
  cep: "40110-100",
  street: "Avenida Sete de Setembro",
  number: "1234",
  complement: "",
  district: "Centro",
  city: "Salvador",
  state: "BA",
};

describe("billingSchema", () => {
  it("normaliza os dados para o formato da API", () => {
    const result = billingSchema.safeParse(valid);
    expect(result.success).toBe(true);
    expect(result.success && result.data).toEqual({
      name: "Ana Maria Souza",
      email: "ana@example.com",
      phone: "71998765432",
      cpf: "52998224725",
      cep: "40110100",
      street: "Avenida Sete de Setembro",
      number: "1234",
      complement: null,
      district: "Centro",
      city: "Salvador",
      state: "BA",
    });
  });

  it("mostra todos os erros em PT-BR, um por campo", () => {
    const result = billingSchema.safeParse({
      name: " ",
      email: "ana@",
      phone: "1234",
      cpf: "529.982.247-24",
      cep: "123",
      street: "",
      number: "",
      complement: "x".repeat(61),
      district: "",
      city: "",
      state: "XX",
    });
    expect(result.success).toBe(false);
    expect(result.success ? {} : fieldErrorsOf(result.error)).toEqual({
      name: "Informe o nome completo.",
      email: "Informe um e-mail válido.",
      phone: "Informe o telefone com DDD.",
      cpf: "CPF inválido.",
      cep: "Informe o CEP com 8 dígitos.",
      street: "Informe o endereço.",
      number: "Informe o número (ou S/N).",
      complement: "Use no máximo 60 caracteres.",
      district: "Informe o bairro.",
      city: "Informe a cidade.",
      state: "Escolha o estado.",
    });
  });

  it("pede o CPF quando ele está vazio", () => {
    const result = billingSchema.safeParse({ ...valid, cpf: "" });
    expect(result.success ? {} : fieldErrorsOf(result.error)).toEqual({ cpf: "Informe o CPF." });
  });
});

describe("phoneDigits", () => {
  it.each([
    ["(71) 99876-5432", "71998765432"],
    ["71 3333-4444", "7133334444"],
    ["+55 71 99876-5432", "71998765432"],
  ])("aceita %j", (raw, digits) => {
    expect(phoneDigits(raw)).toBe(digits);
  });

  it.each(["", "998765432", "(01) 99876-5432", "71 99876-543x", "123456789012"])("recusa %j", (raw) => {
    expect(phoneDigits(raw)).toBeNull();
  });
});

describe("cepDigits", () => {
  it.each([
    ["40110-100", "40110100"],
    ["40110100", "40110100"],
  ])("aceita %j", (raw, digits) => {
    expect(cepDigits(raw)).toBe(digits);
  });

  it.each(["4011-0100", "4011010", "401101000", "abcde-fgh"])("recusa %j", (raw) => {
    expect(cepDigits(raw)).toBeNull();
  });
});

describe("máscaras", () => {
  it.each([
    ["", ""],
    ["7", "(7"],
    ["71", "(71"],
    ["7199", "(71) 99"],
    ["7133334444", "(71) 3333-4444"],
    ["71998765432", "(71) 99876-5432"],
    ["71998765432999", "(71) 99876-5432"],
  ])("telefone %j vira %j", (raw, expected) => {
    expect(formatPhoneInput(raw)).toBe(expected);
  });

  it.each([
    ["", ""],
    ["40110", "40110"],
    ["401101", "40110-1"],
    ["40110100", "40110-100"],
    ["40110-1009", "40110-100"],
  ])("CEP %j vira %j", (raw, expected) => {
    expect(formatCepInput(raw)).toBe(expected);
  });
});
