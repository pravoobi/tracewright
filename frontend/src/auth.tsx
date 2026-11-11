import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import axios from "axios";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

// The browser authenticates with an HttpOnly session cookie set by the
// backend at login -- no credential is ever readable from JavaScript or
// embedded in the bundle. The only secret held here is the CSRF token, which
// lives in memory (never storage) and is re-fetched from /auth/me on load.
axios.defaults.withCredentials = true;

type AuthState =
  | { status: "loading" }
  | { status: "anon" }
  | { status: "authed"; email: string; tenantId: string; csrf: string };

interface AuthContextValue {
  state: AuthState;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

let csrfToken: string | null = null;

axios.interceptors.request.use((config) => {
  const method = (config.method || "get").toLowerCase();
  if (csrfToken && !["get", "head", "options"].includes(method)) {
    config.headers.set("X-CSRF-Token", csrfToken);
  }
  return config;
});

function toAuthed(data: { user: { email: string }; tenant_id: string; csrf_token: string }): AuthState {
  csrfToken = data.csrf_token;
  return { status: "authed", email: data.user.email, tenantId: data.tenant_id, csrf: data.csrf_token };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  useEffect(() => {
    axios
      .get(`${API}/auth/me`)
      .then((r) => setState(toAuthed(r.data)))
      .catch(() => setState({ status: "anon" }));
  }, []);

  // A session that expires or is revoked mid-use: drop back to the login page.
  useEffect(() => {
    const id = axios.interceptors.response.use(undefined, (error) => {
      const url: string = error?.config?.url ?? "";
      if (error?.response?.status === 401 && !url.includes("/auth/")) {
        csrfToken = null;
        setState({ status: "anon" });
      }
      return Promise.reject(error);
    });
    return () => axios.interceptors.response.eject(id);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const r = await axios.post(`${API}/auth/login`, { email, password });
    setState(toAuthed(r.data));
  }, []);

  const logout = useCallback(async () => {
    try {
      await axios.post(`${API}/auth/logout`);
    } finally {
      csrfToken = null;
      setState({ status: "anon" });
    }
  }, []);

  return <AuthContext.Provider value={{ state, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** The signed-in user's tenant. Only call inside the authenticated app. */
export function useTenantId(): string {
  const { state } = useAuth();
  if (state.status !== "authed") throw new Error("useTenantId requires an authenticated session");
  return state.tenantId;
}
