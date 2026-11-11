import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "./auth";
import { Login } from "./pages/Login";
import { IngestionReview } from "./pages/IngestionReview";
import { PlannerReview } from "./pages/PlannerReview";
import { EnvironmentDashboard } from "./pages/EnvironmentDashboard";
import { TestCatalog } from "./pages/TestCatalog";
import "./index.css";

const qc = new QueryClient();

const nav = [
  { to: "/", label: "Ingestion" },
  { to: "/plan", label: "Plan Review" },
  { to: "/tests", label: "Test Catalog" },
  { to: "/environments", label: "Environments" },
];

function App() {
  const { logout, state } = useAuth();
  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200 px-6 py-3 flex gap-6">
        <span className="font-bold text-indigo-700 mr-4">Tracewright</span>
        {nav.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `text-sm ${isActive ? "text-indigo-700 font-medium" : "text-gray-600 hover:text-gray-900"}`
            }
          >
            {label}
          </NavLink>
        ))}
        <span className="ml-auto flex items-center gap-3 text-sm text-gray-600">
          {state.status === "authed" && <span>{state.email}</span>}
          <button onClick={() => void logout()} className="text-indigo-700 hover:underline">
            Sign out
          </button>
        </span>
      </nav>
      <main className="py-8">
        <Routes>
          <Route path="/" element={<IngestionReview />} />
          <Route path="/plan" element={<PlannerReview />} />
          <Route path="/tests" element={<TestCatalog />} />
          <Route path="/environments" element={<EnvironmentDashboard />} />
        </Routes>
      </main>
    </div>
  );
}

function Gate() {
  const { state } = useAuth();
  if (state.status === "loading") return null;
  if (state.status === "anon") return <Login />;
  return <App />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <AuthProvider>
          <Gate />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
