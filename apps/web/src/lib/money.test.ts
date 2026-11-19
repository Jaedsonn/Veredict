import { describe, expect, it } from "vitest";

import { creditsLabel, formatBRL } from "@/lib/money";

describe("formatBRL", () => {
  it.each([
    [2500, "R$ 25,00"],
    [350, "R$ 3,50"],
    [21000, "R$ 210,00"],
  ])("formata %d centavos", (cents, expected) => {
    // O Intl usa espaço não separável entre o símbolo e o valor
    expect(formatBRL(cents).replace(/\s/g, " ")).toBe(expected);
  });
});

describe("creditsLabel", () => {
  it("usa o singular só para 1", () => {
    expect(creditsLabel(1)).toBe("1 crédito");
    expect(creditsLabel(0)).toBe("0 créditos");
    expect(creditsLabel(20)).toBe("20 créditos");
  });
});
