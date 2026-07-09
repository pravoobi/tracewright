import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import axios from "axios";
import { IngestionReview } from "./pages/IngestionReview";
import { PlannerReview } from "./pages/PlannerReview";
import { EnvironmentDashboard } from "./pages/EnvironmentDashboard";
import { TestCatalog } from "./pages/TestCatalog";
import "./index.css";

// Every backend router requires X-API-Key (see backend/src/auth/api_key.py).
// Set once, globally, rather than threading it through every axios call in
// every page/component.
const apiKey = import.meta.env.VITE_TENANT_API_KEY;
if (apiKey) {
  axios.defaults.headers.common["X-API-Key"] = apiKey;
} else {
  console.warn(
    "VITE_TENANT_API_KEY is not set — all API requests will fail with 401."
  );
}

const qc = new QueryClient();

const nav = [
  { to: "/", label: "Ingestion" },
  { to: "/plan", label: "Plan Review" },
  { to: "/tests", label: "Test Catalog" },
  { to: "/environments", label: "Environments" },
];

function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200 px-6 py-3 flex gap-6">
        <span className="font-bold text-indigo-700 mr-4">AI Test Agent</span>
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

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
