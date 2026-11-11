import { redirect } from "next/navigation";

/** A raiz leva ao painel; o proxy.ts manda para /entrar quem não tem sessão. */
export default function Home() {
  redirect("/painel");
}
