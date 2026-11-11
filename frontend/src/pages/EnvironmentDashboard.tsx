import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { useTenantId } from "../auth";
import { CoverageStats } from "../components/CoverageStats";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

interface Environment {
  id: string;
  name: string;
  url: string | null;
  code_version: string;
  doc_version: string | null;
  updated_at: string | null;
  staleness_warning: string | null;
}

export function EnvironmentDashboard() {
  const TENANT_ID = useTenantId();
  const { data: envs = [], isLoading } = useQuery<Environment[]>({
    queryKey: ["environments", TENANT_ID],
    queryFn: () =>
      axios.get(`${API}/environments/${TENANT_ID}`).then((r) => r.data),
  });

  if (isLoading) return <div className="p-8 text-gray-500">Loading…</div>;

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Environments</h1>
      <CoverageStats tenantId={TENANT_ID} />
      <div className="space-y-4">
        {envs.map((env) => (
          <div key={env.id} className="border rounded-lg p-4 bg-white shadow-sm">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="font-semibold text-gray-900">{env.name}</h2>
                {env.url && (
                  <a
                    href={env.url}
                    className="text-sm text-blue-600 hover:underline"
                    target="_blank"
                    rel="noreferrer"
                  >
                    {env.url}
                  </a>
                )}
                <div className="flex gap-4 mt-1 text-xs text-gray-500">
                  <span>Code: v{env.code_version}</span>
                  {env.doc_version && <span>Doc: v{env.doc_version}</span>}
                  {env.updated_at && (
                    <span>Updated: {new Date(env.updated_at).toLocaleDateString()}</span>
                  )}
                </div>
              </div>
            </div>
            {env.staleness_warning && (
              <div className="mt-3 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
                ⚠ {env.staleness_warning}
              </div>
            )}
          </div>
        ))}
        {envs.length === 0 && (
          <div className="text-center py-12 text-gray-400">No environments configured.</div>
        )}
      </div>
    </div>
  );
}
