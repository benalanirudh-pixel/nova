const BASE = "/api";
const TOKEN_KEY = "nova.token";

/** X-Nova-Token for the costly POSTs (/refresh, /interpret) when the server sets NOVA_REFRESH_TOKEN. */
export function authHeaders(): Record<string, string> {
  try { const t = localStorage.getItem(TOKEN_KEY); return t ? { "X-Nova-Token": t } : {}; } catch { return {}; }
}

export async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (res.status === 403 && init?.method === "POST") {
    const body = await res.json().catch(() => null);
    if (/token/i.test(body?.error ?? "")) {
      const t = window.prompt("This server needs the Nova access token (NOVA_REFRESH_TOKEN):");
      if (t) {
        try { localStorage.setItem(TOKEN_KEY, t); } catch { /* storage unavailable */ }
        return fetchJSON<T>(path, { ...init, headers: { ...(init.headers as Record<string, string>), ...authHeaders() } });
      }
    }
    throw new Error(typeof body?.error === "string" ? body.error : `API ${res.status}: ${path}`);
  }
  if (!res.ok) {
    // surface the server's {"error": "..."} when present
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.error === "string" ? body.error : `API ${res.status}: ${path}`);
  }
  return res.json();
}

/** POST JSON with the access token attached. */
export const postJSON = <T,>(path: string, body: unknown) =>
  fetchJSON<T>(path, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify(body) });
