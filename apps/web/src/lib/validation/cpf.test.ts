import { describe, expect, it } from "vitest";

import { cpfDigits, cpfLiveError, formatCpfInput, hideCpf } from "@/lib/validation/cpf";

import vectors from "./cpf-vectors.json";

// Os mesmos vetores de services/auth/tests/test_cpf_oab.py: as duas validações não divergem
describe("cpfDigits", () => {
  it.each(vectors.valid)("aceita $input", ({ input, digits, masked }) => {
    expect(cpfDigits(input)).toBe(digits);
    expect(hideCpf(digits)).toBe(masked);
  });

  it.each(vectors.invalid)("recusa %j", (input) => {
    expect(cpfDigits(input)).toBeNull();
  });

  it.each([null, undefined, 52998224725, ["52998224725"]])("recusa o não texto %j", (input) => {
    expect(cpfDigits(input)).toBeNull();
  });

  it.each("0123456789".split(""))("recusa 11 dígitos %s repetidos", (digit) => {
    expect(cpfDigits(digit.repeat(11))).toBeNull();
  });
});

describe("formatCpfInput", () => {
  it.each([
    ["", ""],
    ["529", "529"],
    ["5299", "529.9"],
    ["5299822", "529.982.2"],
    ["5299822472", "529.982.247-2"],
    ["52998224725", "529.982.247-25"],
    ["529.982.247-25999", "529.982.247-25"],
    ["529a982 247/25", "529.982.247-25"],
  ])("formata %j como %j", (raw, expected) => {
    expect(formatCpfInput(raw)).toBe(expected);
  });

  it("gera sempre um texto que o validador aceita", () => {
    expect(cpfDigits(formatCpfInput("52998224725"))).toBe("52998224725");
  });
});

describe("cpfLiveError", () => {
  it.each([
    ["", false],
    ["", true],
    ["529.98", false],
    ["529.982.247-25", false],
    ["529.982.247-25", true],
  ])("não acusa %j (saiu do campo: %s)", (value, blurred) => {
    expect(cpfLiveError(value, blurred)).toBeUndefined();
  });

  it("acusa o CPF incompleto só depois de sair do campo", () => {
    expect(cpfLiveError("529.982.24", true)).toBe("Informe os 11 dígitos do CPF.");
  });

  it.each([false, true])("acusa dígitos verificadores errados assim que completa (saiu: %s)", (blurred) => {
    expect(cpfLiveError("529.982.247-24", blurred)).toBe("CPF inválido.");
    expect(cpfLiveError("111.111.111-11", blurred)).toBe("CPF inválido.");
  });
});
