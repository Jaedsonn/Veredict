// Gateway MOCK para desenvolver a web sem o backend (#12: "pode começar com o gateway mockado").
// Implementa em memória os contratos da Sprint 1 (#7, #8, #9, #10, #11), a recuperação de senha (#19)
// e o cadastro com tipo, CPF e OAB (#60). O CPF nunca vai para o console.
// NÃO usar em produção. Uso: npm run mock:gateway -w @veriditi/web  (porta 8080)
// Os códigos de verificação e os links de redefinição aparecem no console (no lugar do Mailpit).

import { createServer } from "node:http";
import { randomBytes, randomInt, randomUUID } from "node:crypto";

const PORT = Number(process.env.MOCK_GATEWAY_PORT ?? 8080);
const ACCESS_TTL_S = Number(process.env.MOCK_ACCESS_TTL_S ?? 900);

const users = new Map(); // email -> user
const codes = new Map(); // email -> { code, expiresAt, attempts }
const access = new Map(); // token -> { userId, exp }
const refresh = new Map(); // token -> { userId, family, revoked, exp }
const loginHits = new Map(); // ip|email -> timestamps
const resetTokens = new Map(); // token -> { email, expiresAt, used }
const forgotHits = new Map(); // email -> timestamps
const WEB_URL = process.env.MOCK_WEB_URL ?? "http://localhost:3000";
let nextId = 1;

const send = (res, status, body, headers = {}) => {
  res.writeHead(status, { "Content-Type": "application/json", ...headers });
  res.end(body === undefined ? "" : JSON.stringify(body));
};
const fail = (res, status, code, message, extra = {}, headers = {}) =>
  send(res, status, { detail: { code, message, ...extra } }, headers);
const invalid = (res, field, msg) =>
  send(res, 422, { detail: [{ loc: ["body", ...field.split(".")], msg, type: "value_error" }] });

const readBody = (req) =>
  new Promise((resolve) => {
    let data = "";
    req.on("data", (c) => (data += c));
    req.on("end", () => {
      try {
        resolve(data ? JSON.parse(data) : {});
      } catch {
        resolve(null);
      }
    });
  });

const publicUser = (u) => ({
  id: u.id,
  name: u.name,
  email: u.email,
  status: u.status,
  email_verified_at: u.emailVerifiedAt,
  created_at: u.createdAt,
  user_type: u.userType,
  cpf_masked: `***.${u.cpf.slice(3, 6)}.${u.cpf.slice(6, 9)}-**`,
  oab: u.oab,
});

// Versão curta do value object Cpf do auth; os vetores completos estão em cpf-vectors.json
const cpfDigits = (raw) => {
  if (typeof raw !== "string" || !/^\d{3}\.?\d{3}\.?\d{3}-?\d{2}$/.test(raw.trim())) return null;
  const d = raw.trim().replace(/[.-]/g, "");
  if (/^(\d)\1{10}$/.test(d)) return null;
  const dv = (s) => ([...s].reduce((t, c, i) => t + Number(c) * (s.length + 1 - i), 0) * 10) % 11 % 10;
  const first = dv(d.slice(0, 9));
  return d.slice(9) === `${first}${dv(d.slice(0, 9) + first)}` ? d : null;
};

const OAB_UFS = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split(" ");
const OAB_KINDS = ["principal", "suplementar", "transitoria"];

const newCode = (email) => {
  const code = String(randomInt(0, 1_000_000)).padStart(6, "0");
  codes.set(email, { code, expiresAt: Date.now() + 15 * 60_000, attempts: 0, sentAt: Date.now() });
  console.log(`\n[mock] código de verificação para ${email}: ${code}\n`);
};

const issueTokens = (userId, family = randomUUID()) => {
  const at = randomBytes(24).toString("base64url");
  const rt = randomBytes(32).toString("base64url");
  access.set(at, { userId, exp: Date.now() + ACCESS_TTL_S * 1000 });
  refresh.set(rt, { userId, family, revoked: false, exp: Date.now() + 7 * 86400_000 });
  return { access_token: at, refresh_token: rt, expires_in: ACCESS_TTL_S };
};

const authUser = (req) => {
  const token = (req.headers.authorization ?? "").replace(/^Bearer /, "");
  const entry = access.get(token);
  if (!entry || entry.exp < Date.now()) return null;
  return [...users.values()].find((u) => u.id === entry.userId) ?? null;
};

const passwordProblem = (p) => {
  if (typeof p !== "string" || p.length < 10) return "A senha deve ter pelo menos 10 caracteres.";
  if (!/\p{L}/u.test(p)) return "A senha deve conter pelo menos 1 letra.";
  if (!/\d/.test(p)) return "A senha deve conter pelo menos 1 número.";
  return null;
};

const routes = {
  "GET /health/ready": (_req, res) => send(res, 200, { status: "ok", services: { auth: "up" } }),

  "POST /api/auth/register": async (req, res, b) => {
    const email = String(b.email ?? "").trim().toLowerCase();
    const name = String(b.name ?? "").trim();
    if (!name) return invalid(res, "name", "Informe seu nome.");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return invalid(res, "email", "E-mail inválido.");
    const pw = passwordProblem(b.password);
    if (pw) return invalid(res, "password", pw);
    if (!["common", "lawyer"].includes(b.user_type)) return invalid(res, "user_type", "Escolha o tipo de conta.");
    const cpf = cpfDigits(b.cpf);
    if (!cpf) return invalid(res, "cpf", "CPF inválido.");
    let oab = null;
    if (b.user_type === "common" && b.oab != null) return invalid(res, "oab", "Só advogados informam OAB.");
    if (b.user_type === "lawyer") {
      if (!b.oab || typeof b.oab !== "object") return invalid(res, "oab", "Informe a inscrição na OAB.");
      const number = String(b.oab.number ?? "").trim();
      const uf = String(b.oab.uf ?? "").trim().toUpperCase();
      const kind = String(b.oab.kind ?? "").trim().toLowerCase();
      if (!/^\d{1,6}$/.test(number) || Number(number) === 0)
        return invalid(res, "oab.number", "Informe o número da OAB com até 6 dígitos.");
      if (!OAB_UFS.includes(uf)) return invalid(res, "oab.uf", "Escolha a UF da seccional.");
      if (!OAB_KINDS.includes(kind)) return invalid(res, "oab.kind", "Escolha o tipo de inscrição.");
      oab = { number: String(Number(number)), uf, kind };
    }
    const all = [...users.values()];
    if (users.has(email)) return fail(res, 409, "email_already_registered", "E-mail já cadastrado.", { field: "email" });
    if (all.some((u) => u.cpf === cpf))
      return fail(res, 409, "cpf_already_registered", "Este CPF já está cadastrado.", { field: "cpf" });
    if (oab && all.some((u) => u.oab?.uf === oab.uf && u.oab?.number === oab.number))
      return fail(res, 409, "oab_already_registered", "Esta inscrição na OAB já está cadastrada.", { field: "oab" });
    const user = {
      id: nextId++,
      name,
      email,
      password: b.password,
      status: "pending_verification",
      emailVerifiedAt: null,
      createdAt: new Date().toISOString(),
      userType: b.user_type,
      cpf,
      oab,
    };
    users.set(email, user);
    newCode(email);
    send(res, 201, { id: user.id, email, status: user.status, user_type: user.userType });
  },

  "POST /api/auth/verify-email": async (_req, res, b) => {
    const email = String(b.email ?? "").trim().toLowerCase();
    const entry = codes.get(email);
    const user = users.get(email);
    if (!entry || !user) return fail(res, 400, "code_expired", "Código expirado.");
    if (entry.expiresAt < Date.now()) return fail(res, 400, "code_expired", "Código expirado.");
    if (entry.attempts >= 5) return fail(res, 400, "too_many_attempts", "Código bloqueado.");
    if (entry.code !== b.code) {
      entry.attempts += 1;
      return fail(res, 400, "invalid_code", "Código incorreto.", { attempts_remaining: 5 - entry.attempts });
    }
    codes.delete(email);
    user.status = "active";
    user.emailVerifiedAt = new Date().toISOString();
    send(res, 200, { status: "active" });
  },

  "POST /api/auth/verify-email/resend": async (_req, res, b) => {
    const email = String(b.email ?? "").trim().toLowerCase();
    const user = users.get(email);
    const last = codes.get(email);
    if (last && Date.now() - last.sentAt < 60_000) {
      const wait = Math.ceil((60_000 - (Date.now() - last.sentAt)) / 1000);
      return send(res, 429, { detail: "Aguarde para reenviar." }, { "Retry-After": String(wait) });
    }
    if (user?.status === "pending_verification") newCode(email);
    send(res, 202, { status: "accepted" });
  },

  "POST /api/auth/login": async (req, res, b) => {
    const email = String(b.email ?? "").trim().toLowerCase();
    const key = `${req.socket.remoteAddress}|${email}`;
    const hits = (loginHits.get(key) ?? []).filter((t) => Date.now() - t < 60_000);
    if (hits.length >= 5) {
      const wait = Math.ceil((60_000 - (Date.now() - hits[0])) / 1000);
      return send(res, 429, { detail: "Muitas tentativas." }, { "Retry-After": String(wait) });
    }
    loginHits.set(key, [...hits, Date.now()]);
    const user = users.get(email);
    if (!user || user.password !== b.password)
      return fail(res, 401, "invalid_credentials", "E-mail ou senha incorretos.");
    if (user.status === "pending_verification")
      return send(res, 403, { code: "email_not_verified", detail: "E-mail não verificado." });
    send(res, 200, issueTokens(user.id));
  },

  "POST /api/auth/password/forgot": async (_req, res, b) => {
    const email = String(b.email ?? "").trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return invalid(res, "email", "Informe um e-mail válido.");
    // 3 por hora por e-mail, como o gateway real (#19).
    const hits = (forgotHits.get(email) ?? []).filter((t) => Date.now() - t < 3_600_000);
    if (hits.length >= 3) {
      const wait = Math.ceil((3_600_000 - (Date.now() - hits[0])) / 1000);
      return send(res, 429, { detail: "Muitas tentativas." }, { "Retry-After": String(wait) });
    }
    forgotHits.set(email, [...hits, Date.now()]);
    // 202 sempre: só conta ativa recebe link, e um pedido novo invalida os anteriores.
    if (users.get(email)?.status === "active") {
      for (const entry of resetTokens.values()) if (entry.email === email) entry.used = true;
      const token = randomBytes(32).toString("base64url");
      resetTokens.set(token, { email, expiresAt: Date.now() + 30 * 60_000, used: false });
      console.log(`\n[mock] link de redefinição para ${email}: ${WEB_URL}/redefinir-senha?token=${token}\n`);
    }
    send(res, 202, { status: "accepted" });
  },

  "POST /api/auth/password/reset": async (_req, res, b) => {
    const entry = resetTokens.get(String(b.token ?? ""));
    const pw = passwordProblem(b.new_password);
    if (pw) return invalid(res, "new_password", pw);
    if (!entry || entry.used || entry.expiresAt < Date.now() || users.get(entry.email)?.status !== "active")
      return fail(res, 400, "invalid_reset_token", "Link inválido ou expirado. Solicite um novo.");
    const user = users.get(entry.email);
    entry.used = true;
    user.password = b.new_password;
    // Todas as sessões do usuário caem, como no auth.
    for (const r of refresh.values()) if (r.userId === user.id) r.revoked = true;
    for (const [at, a] of access) if (a.userId === user.id) access.delete(at);
    console.log(`[mock] senha de ${user.email} redefinida; sessões revogadas`);
    send(res, 204);
  },

  "POST /api/auth/refresh": async (_req, res, b) => {
    const entry = refresh.get(b.refresh_token);
    if (!entry || entry.exp < Date.now()) return fail(res, 401, "invalid_refresh", "Refresh inválido.");
    if (entry.revoked) {
      // Reuso detectado: revoga a família inteira (#9).
      for (const r of refresh.values()) if (r.family === entry.family) r.revoked = true;
      console.log("[mock] reuso de refresh token detectado; sessões revogadas");
      return fail(res, 401, "refresh_reuse_detected", "Sessão revogada.");
    }
    entry.revoked = true;
    send(res, 200, issueTokens(entry.userId, entry.family));
  },

  "POST /api/auth/logout": async (req, res, b) => {
    if (!authUser(req)) return fail(res, 401, "unauthorized", "Não autenticado.");
    const entry = refresh.get(b.refresh_token);
    if (entry) entry.revoked = true;
    send(res, 204);
  },

  "GET /api/me": (req, res) => {
    const user = authUser(req);
    if (!user) return fail(res, 401, "unauthorized", "Não autenticado.");
    send(res, 200, publicUser(user));
  },

  "PATCH /api/me": async (req, res, b) => {
    const user = authUser(req);
    if (!user) return fail(res, 401, "unauthorized", "Não autenticado.");
    if (b.name !== undefined) {
      const name = String(b.name).trim();
      if (!name || name.length > 120) return invalid(res, "name", "Nome inválido.");
      user.name = name;
    }
    send(res, 200, publicUser(user));
  },

  "POST /api/me/password": async (req, res, b) => {
    const user = authUser(req);
    if (!user) return fail(res, 401, "unauthorized", "Não autenticado.");
    if (b.current_password !== user.password)
      return fail(res, 400, "invalid_current_password", "Senha atual incorreta.");
    const pw = passwordProblem(b.new_password);
    if (pw) return invalid(res, "new_password", pw);
    user.password = b.new_password;
    send(res, 204);
  },
};

createServer(async (req, res) => {
  const path = new URL(req.url ?? "/", "http://x").pathname;
  const handler = routes[`${req.method} ${path}`];
  const started = Date.now();
  res.on("finish", () =>
    console.log(`[mock] ${req.method} ${path} -> ${res.statusCode} (${Date.now() - started} ms)`),
  );
  if (!handler) return send(res, 404, { detail: "Not Found" });
  const body = req.method === "GET" ? {} : await readBody(req);
  if (body === null) return send(res, 422, { detail: "JSON inválido" });
  await handler(req, res, body);
}).listen(PORT, () => console.log(`[mock] gateway em http://localhost:${PORT}`));
