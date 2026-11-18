import { describe, expect, it } from "vitest";

import { parseApiError } from "@/lib/errors";

describe("parseApiError", () => {
  it("junta o loc aninhado da OAB com ponto", () => {
    const error = parseApiError(422, {
      detail: [
        { loc: ["body", "oab", "number"], msg: "Informe o número da OAB com até 6 dígitos." },
        { loc: ["body", "cpf"], msg: "CPF inválido." },
      ],
    });

    expect(error.fieldErrors).toEqual({
      "oab.number": "Informe o número da OAB com até 6 dígitos.",
      cpf: "CPF inválido.",
    });
  });

  it.each([
    ["email_already_registered", "Este e-mail já está cadastrado."],
    ["cpf_already_registered", "Este CPF já está cadastrado."],
    ["oab_already_registered", "Esta inscrição na OAB já está cadastrada."],
  ])("traduz o 409 %s", (code, message) => {
    const error = parseApiError(409, { detail: { code, message: "em inglês", field: "x" } });

    expect(error).toMatchObject({ status: 409, code, message });
  });

  it("dá uma mensagem neutra para um 409 sem code conhecido", () => {
    expect(parseApiError(409, {}).message).toBe("Estes dados já estão cadastrados.");
  });
});
