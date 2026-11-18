import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Gera .next/standalone com um server.js mínimo -> imagem Docker enxuta.
  output: "standalone",
  // No monorepo o node_modules fica na raiz (hoisting do npm workspaces);
  // o tracing precisa partir de lá para copiar as dependências corretas.
  outputFileTracingRoot: path.join(__dirname, "../.."),
  cacheComponents: true,
  // O token de /redefinir-senha está na URL: não vai no Referer nem fica em cache (#19).
  async headers() {
    return [
      {
        source: "/redefinir-senha",
        headers: [
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "Cache-Control", value: "no-store" },
        ],
      },
    ];
  },
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
