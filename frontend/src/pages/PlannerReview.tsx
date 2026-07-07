import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";
const TENANT_ID = import.meta.env.VITE_TENANT_ID || "default-tenant";

interface TestCard {
  id: string;
  test_id: string;
  title: string;
  description: string;
  priority: string;
  test_type: string;
  approval_status: string;
  setup_manifest: object[];
  tier_sources: { tier: number; confidence: number };
  introduced_in_version: string;
}

export function PlannerReview() {
  const qc = useQueryClient();
  const [generating, setGenerating] = useState(false);
  const [featureArea, setFeatureArea] = useState("");
  const [docVersion, setDocVersion] = useState("1.0");
  const [coverageGaps, setCoverageGaps] = useState<string[]>([]);
  const [clarificationFlags, setClarificationFlags] = useState<string[]>([]);

  const { data: cards = [], isLoading } = useQuery<TestCard[]>({
    queryKey: ["test-cards", TENANT_ID, "pending"],
    queryFn: () =>
      axios
        .get(`${API}/plans/${TENANT_ID}/cards?approval_status=pending`)
        .then((r) => r.data),
  });

  const generatePlan = async () => {
    setGenerating(true);
    try {
      const { data } = await axios.post(`${API}/plans/${TENANT_ID}/generate`, {
        feature_area: featureArea,
        doc_version: docVersion,
      });
      setCoverageGaps(data.coverage_gaps ?? []);
      setClarificationFlags(data.clarification_flags ?? []);
      qc.invalidateQueries({ queryKey: ["test-cards"] });
    } finally {
      setGenerating(false);
    }
  };

  const reviewCard = useMutation({
    mutationFn: ({
      cardId,
      action,
    }: {
      cardId: string;
      action: "approve" | "reject";
    }) =>
      axios.patch(`${API}/plans/${TENANT_ID}/cards/${cardId}/review`, {
        action,
        approved_by: "reviewer",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["test-cards"] }),
  });

  const bulkApprove = useMutation({
    mutationFn: (cardIds: string[]) =>
      axios.post(`${API}/plans/${TENANT_ID}/cards/bulk-review`, {
        card_ids: cardIds,
        action: "approve",
        approved_by: "reviewer",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["test-cards"] }),
  });

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Planner Review</h1>

      {/* Generate plan */}
      <div className="border border-gray-200 rounded-lg p-4 mb-6 bg-gray-50">
        <h2 className="text-sm font-semibold mb-3">Generate Test Plan</h2>
        <div className="flex gap-2">
          <input
            className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm"
            placeholder="Feature area (e.g. 'discount codes checkout')"
            value={featureArea}
            onChange={(e) => setFeatureArea(e.target.value)}
          />
          <input
            className="w-24 border border-gray-300 rounded px-3 py-2 text-sm"
            placeholder="Doc v"
            value={docVersion}
            onChange={(e) => setDocVersion(e.target.value)}
          />
          <button
            onClick={generatePlan}
            disabled={generating || !featureArea}
            className="px-4 py-2 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
          >
            {generating ? "Generating…" : "Generate"}
          </button>
        </div>
      </div>

      {/* Clarification flags and coverage gaps from the last generation */}
      {clarificationFlags.length > 0 && (
        <div className="border border-amber-300 bg-amber-50 rounded-lg p-4 mb-4">
          <h2 className="text-sm font-semibold text-amber-900 mb-2">
            Needs clarification ({clarificationFlags.length})
          </h2>
          <ul className="list-disc list-inside space-y-1 text-sm text-amber-900">
            {clarificationFlags.map((flag, i) => (
              <li key={i}>{flag}</li>
            ))}
          </ul>
        </div>
      )}
      {coverageGaps.length > 0 && (
        <div className="border border-blue-200 bg-blue-50 rounded-lg p-4 mb-4">
          <h2 className="text-sm font-semibold text-blue-900 mb-2">
            Coverage gaps ({coverageGaps.length})
          </h2>
          <ul className="list-disc list-inside space-y-1 text-sm text-blue-900">
            {coverageGaps.map((gap, i) => (
              <li key={i}>{gap}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Bulk approve */}
      {cards.length > 0 && (
        <div className="flex justify-between items-center mb-4">
          <span className="text-sm text-gray-500">{cards.length} cards pending review</span>
          <button
            onClick={() => bulkApprove.mutate(cards.map((c) => c.id))}
            className="px-3 py-1.5 text-sm bg-green-600 text-white rounded hover:bg-green-700"
          >
            Approve All
          </button>
        </div>
      )}

      {/* Cards */}
      <div className="space-y-4">
        {isLoading && <div className="text-gray-500">Loading…</div>}
        {cards.map((card) => (
          <div key={card.id} className="border border-gray-200 rounded-lg p-4 bg-white shadow-sm">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-mono text-gray-500">{card.test_id}</span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded font-medium ${
                      card.priority === "P0"
                        ? "bg-red-100 text-red-800"
                        : card.priority === "P1"
                        ? "bg-orange-100 text-orange-800"
                        : "bg-gray-100 text-gray-700"
                    }`}
                  >
                    {card.priority}
                  </span>
                  <span className="text-xs text-gray-500">{card.test_type}</span>
                  <span className="text-xs text-gray-400">
                    v{card.introduced_in_version} · Tier {card.tier_sources?.tier}
                  </span>
                </div>
                <h3 className="font-semibold text-gray-900 mb-1">{card.title}</h3>
                <p className="text-sm text-gray-700 mb-2">{card.description}</p>
                {card.setup_manifest?.length > 0 && (
                  <div className="text-xs text-gray-500 bg-gray-50 rounded p-2">
                    <span className="font-medium">Setup:</span>{" "}
                    {JSON.stringify(card.setup_manifest)}
                  </div>
                )}
              </div>
              <div className="flex flex-col gap-1.5 shrink-0">
                <button
                  onClick={() => reviewCard.mutate({ cardId: card.id, action: "approve" })}
                  className="px-3 py-1.5 text-xs bg-green-600 text-white rounded hover:bg-green-700"
                >
                  Approve
                </button>
                <button
                  onClick={() => reviewCard.mutate({ cardId: card.id, action: "reject" })}
                  className="px-3 py-1.5 text-xs bg-red-600 text-white rounded hover:bg-red-700"
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
        ))}
        {!isLoading && cards.length === 0 && (
          <div className="text-center py-12 text-gray-400">
            No pending test cards. Generate a plan above.
          </div>
        )}
      </div>
    </div>
  );
}
