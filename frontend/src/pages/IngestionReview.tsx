import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { useTenantId } from "../auth";
import { ColumnMapper } from "../components/ColumnMapper";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

interface Chunk {
  id: string;
  logical_id: string;
  chunk_type: string;
  content: string;
  display_ref: string;
  section_path: string;
  confidence: number;
  review_status: string;
}

interface Artifact {
  id: string;
  filename: string;
  type: string;
  status: string;
  unmapped_columns: string[];
}

export function IngestionReview() {
  const TENANT_ID = useTenantId();
  const qc = useQueryClient();
  const [reviewStartTimes, setReviewStartTimes] = useState<Record<string, number>>({});

  const { data: chunks = [], isLoading } = useQuery<Chunk[]>({
    queryKey: ["chunks", TENANT_ID, "pending"],
    queryFn: () =>
      axios
        .get(`${API}/ingestion/${TENANT_ID}/chunks?review_status=pending`)
        .then((r) => r.data),
  });

  // Records when each chunk first appeared in the reviewer's queue, so
  // review_duration_ms reflects actual time-to-decision rather than the
  // ~0ms gap between two Date.now() calls made back-to-back at submit time.
  useEffect(() => {
    const newStarts: Record<string, number> = {};
    for (const c of chunks) {
      if (!(c.id in reviewStartTimes)) newStarts[c.id] = Date.now();
    }
    if (Object.keys(newStarts).length > 0) {
      setReviewStartTimes((prev) => ({ ...prev, ...newStarts }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chunks]);

  const { data: artifacts = [] } = useQuery<Artifact[]>({
    queryKey: ["artifacts", TENANT_ID],
    queryFn: () => axios.get(`${API}/ingestion/${TENANT_ID}/artifacts`).then((r) => r.data),
  });

  const bugExportsNeedingMapping = artifacts.filter(
    (a) => a.type === "bug_export" && a.unmapped_columns.length > 0
  );

  const oversized = artifacts.filter((a) => a.status === "error_oversized");
  const confirmOversized = useMutation({
    mutationFn: (artifactId: string) =>
      axios.post(`${API}/ingestion/${TENANT_ID}/artifacts/${artifactId}/confirm-oversized`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["artifacts", TENANT_ID] }),
  });

  const reviewMutation = useMutation({
    mutationFn: ({
      chunkId,
      action,
    }: {
      chunkId: string;
      action: "approve" | "reject" | "needs_clarification";
    }) => {
      const startTime = reviewStartTimes[chunkId] || Date.now();
      return axios.patch(
        `${API}/ingestion/${TENANT_ID}/chunks/${chunkId}/review`,
        {
          action,
          review_duration_ms: Date.now() - startTime,
        }
      );
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chunks"] }),
  });

  const bulkApprove = useMutation({
    mutationFn: (chunkIds: string[]) =>
      axios.post(`${API}/ingestion/${TENANT_ID}/chunks/bulk-review`, {
        chunk_ids: chunkIds,
        action: "approve",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chunks"] }),
  });

  if (isLoading) return <div className="p-8 text-gray-500">Loading chunks…</div>;

  const pendingChunks = chunks.filter((c) => c.review_status === "pending");

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Ingestion Review</h1>
        <div className="flex gap-2">
          <span className="text-sm text-gray-500">{pendingChunks.length} pending</span>
          <button
            onClick={() => bulkApprove.mutate(pendingChunks.map((c) => c.id))}
            className="px-3 py-1.5 text-sm bg-green-600 text-white rounded-md hover:bg-green-700"
          >
            Approve All
          </button>
        </div>
      </div>

      {oversized.map((a) => (
        <div key={a.id} className="mb-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm">
          <span className="font-medium">{a.filename}</span> is larger than the page limit and was not
          processed. Processing it uses LLM budget for every page.
          <button
            className="ml-3 rounded bg-amber-600 px-2 py-1 text-white disabled:opacity-50"
            disabled={confirmOversized.isPending}
            onClick={() => confirmOversized.mutate(a.id)}
          >
            Process anyway
          </button>
          {confirmOversized.isError && (
            <span className="ml-2 text-red-700">Could not start processing.</span>
          )}
        </div>
      ))}

      {bugExportsNeedingMapping.map((a) => (
        <ColumnMapper key={a.id} tenantId={TENANT_ID} artifactId={a.id} filename={a.filename} />
      ))}

      <div className="space-y-4">
        {pendingChunks.map((chunk) => (
          <div
            key={chunk.id}
            className="border border-gray-200 rounded-lg p-4 bg-white shadow-sm"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-medium px-2 py-0.5 rounded bg-blue-100 text-blue-800">
                    {chunk.chunk_type}
                  </span>
                  <span className="text-xs text-gray-500">{chunk.display_ref}</span>
                  <span
                    className={`text-xs ${
                      chunk.confidence >= 0.85
                        ? "text-green-600"
                        : chunk.confidence >= 0.6
                        ? "text-yellow-600"
                        : "text-red-600"
                    }`}
                  >
                    {Math.round(chunk.confidence * 100)}% confident
                  </span>
                </div>
                <p className="text-sm text-gray-800 whitespace-pre-wrap">{chunk.content}</p>
                {chunk.section_path && (
                  <p className="text-xs text-gray-400 mt-1">{chunk.section_path}</p>
                )}
              </div>
              <div className="flex flex-col gap-1.5 shrink-0">
                <button
                  onClick={() => reviewMutation.mutate({ chunkId: chunk.id, action: "approve" })}
                  className="px-3 py-1.5 text-xs bg-green-600 text-white rounded hover:bg-green-700"
                >
                  Approve
                </button>
                <button
                  onClick={() =>
                    reviewMutation.mutate({ chunkId: chunk.id, action: "needs_clarification" })
                  }
                  className="px-3 py-1.5 text-xs bg-yellow-500 text-white rounded hover:bg-yellow-600"
                >
                  Clarify
                </button>
                <button
                  onClick={() => reviewMutation.mutate({ chunkId: chunk.id, action: "reject" })}
                  className="px-3 py-1.5 text-xs bg-red-600 text-white rounded hover:bg-red-700"
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
        ))}

        {pendingChunks.length === 0 && (
          <div className="text-center py-12 text-gray-400">
            No pending chunks — all reviewed.
          </div>
        )}
      </div>
    </div>
  );
}
