import path from "node:path";
import { defineConfig } from "vitest/config";

// Só funções puras de src/lib por enquanto; componentes e Server Actions ficam para o E2E.
export default defineConfig({
  resolve: {
    alias: { "@": path.join(__dirname, "src") },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
