import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

const CANONICAL_FIELDS = [
  "external_id", "title", "description", "severity", "component",
  "status", "root_cause", "fix_version", "linked_story", "closed_at",
];

interface Props {
  tenantId: string;
  artifactId: string;
  filename: string;
}

export function ColumnMapper({ tenantId, artifactId, filename }: Props) {
  const qc = useQueryClient();
  const [mapping, setMapping] = useState<Record<string, string>>({});

  const { data, isLoading } = useQuery<{
    unmapped_columns: string[];
    suggested_mapping: Record<string, string | null>;
  }>({
    queryKey: ["column-mapping", tenantId, artifactId],
    queryFn: () =>
      axios
        .get(`${API}/ingestion/${tenantId}/bug-exports/${artifactId}/column-mapping`)
        .then((r) => r.data),
  });

  useEffect(() => {
    if (data?.suggested_mapping) {
      const initial: Record<string, string> = {};
      for (const col of data.unmapped_columns) {
        initial[col] = data.suggested_mapping[col] || "";
      }
      setMapping(initial);
    }
  }, [data]);

  const confirmMutation = useMutation({
    mutationFn: () =>
      // Send every reviewed column, including ones explicitly left
      // unmapped (empty string) — that's a real, distinct decision ("this
      // column has no canonical equivalent") that must be remembered, not
      // the same as "never reviewed at all".
      axios.post(`${API}/ingestion/${tenantId}/bug-exports/${artifactId}/column-mapping`, {
        mapping,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["artifacts"] });
      qc.invalidateQueries({ queryKey: ["column-mapping", tenantId, artifactId] });
    },
  });

  if (isLoading) return null;
  if (!data || data.unmapped_columns.length === 0) return null;

  return (
    <div className="border border-amber-300 bg-amber-50 rounded-lg p-4 mb-4">
      <h2 className="text-sm font-semibold text-amber-900 mb-1">
        Column mapping needed — {filename}
      </h2>
      <p className="text-xs text-amber-800 mb-3">
        These spreadsheet columns weren't recognized. Confirm the mapping once and it'll
        apply automatically to future uploads of this same export format.
      </p>
      <div className="space-y-2">
        {data.unmapped_columns.map((col) => (
          <div key={col} className="flex items-center gap-3">
            <span className="text-sm font-mono text-gray-700 w-48 truncate">{col}</span>
            <span className="text-gray-400">→</span>
            <select
              value={mapping[col] ?? ""}
              onChange={(e) => setMapping((m) => ({ ...m, [col]: e.target.value }))}
              className="text-sm border border-gray-300 rounded px-2 py-1 flex-1"
            >
              <option value="">(leave unmapped)</option>
              {CANONICAL_FIELDS.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>
      <button
        onClick={() => confirmMutation.mutate()}
        disabled={confirmMutation.isPending}
        className="mt-3 px-3 py-1.5 text-sm bg-amber-600 text-white rounded-md hover:bg-amber-700 disabled:opacity-50"
      >
        {confirmMutation.isPending ? "Saving…" : "Confirm mapping"}
      </button>
      {confirmMutation.isSuccess && (
        <span className="ml-3 text-sm text-green-700">
          Saved — {confirmMutation.data.data.bugs_ingested} bugs re-ingested.
        </span>
      )}
      {confirmMutation.isError && (
        <span className="ml-3 text-sm text-red-700">
          Failed to save:{" "}
          {axios.isAxiosError(confirmMutation.error)
            ? confirmMutation.error.response?.data?.detail ?? confirmMutation.error.message
            : String(confirmMutation.error)}
        </span>
      )}
    </div>
  );
}
