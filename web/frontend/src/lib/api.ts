const BASE = "/api";
export async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    // surface the server's {"error": "..."} when present
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.error === "string" ? body.error : `API ${res.status}: ${path}`);
  }
  return res.json();
}
