import { describe, expect, it } from "vitest";

import { publicValues } from "@/lib/form-state";

describe("publicValues", () => {
  it("não devolve senha, código nem CPF ao navegador", () => {
    const values = {
      name: "Maria",
      email: "maria@example.com",
      userType: "lawyer",
      oabNumber: "12345",
      password: "SenhaForte123",
      confirmPassword: "SenhaForte123",
      code: "123456",
      cpf: "529.982.247-25",
      $ACTION_ID_abc: "x",
    };

    expect(publicValues(values)).toEqual({
      name: "Maria",
      email: "maria@example.com",
      userType: "lawyer",
      oabNumber: "12345",
    });
  });
});
