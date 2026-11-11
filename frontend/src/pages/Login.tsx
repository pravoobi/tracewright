import { useState } from "react";
import axios from "axios";
import { useAuth } from "../auth";

export function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      setError(
        status === 429
          ? "Too many failed attempts. Try again in a few minutes."
          : status === 401
            ? "Invalid email or password."
            : "Could not sign in. Check that the backend is running."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm bg-white border border-gray-200 rounded-lg p-6 space-y-4">
        <h1 className="text-xl font-bold text-indigo-700">Tracewright</h1>
        <label className="block text-sm text-gray-700">
          Email
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full border border-gray-300 rounded px-3 py-2"
          />
        </label>
        <label className="block text-sm text-gray-700">
          Password
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full border border-gray-300 rounded px-3 py-2"
          />
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-700">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="w-full bg-indigo-600 text-white rounded px-3 py-2 disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
