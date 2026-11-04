import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Gera .next/standalone com um server.js mínimo -> imagem Docker enxuta.
  output: "standalone",
  // No monorepo o node_modules fica na raiz (hoisting do npm workspaces);
  // o tracing precisa partir de lá para copiar as dependências corretas.
  outputFileTracingRoot: path.join(__dirname, "../.."),
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    root: path.join(__dirname, "../.."),
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
