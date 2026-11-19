import { describe, expect, it } from "vitest";

import { safeNext } from "@/lib/safe-redirect";

describe("safeNext", () => {
  it.each(["/perfil", "/painel?aba=1"])("aceita o caminho interno %s", (next) => {
    expect(safeNext(next)).toBe(next);
  });

  it.each([null, undefined, "", "perfil", "//evil.com", "https://evil.com", "/\\evil.com"])(
    "troca %s pelo destino padrão",
    (next) => {
      expect(safeNext(next)).toBe("/painel");
    },
  );
});
