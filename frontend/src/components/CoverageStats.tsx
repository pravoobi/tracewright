import { useQuery } from "@tanstack/react-query";
import axios from "axios";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

interface Metrics {
  review_time: { chunk_median_ms: number | null; test_card_median_ms: number | null };
  chunk_auto_approval_rate: number | null;
  chunks_total: number;
  chunks_auto_approved: number;
  human_edits: {
    avg_edits_per_test_card: number | null;
    edit_rate: number | null;
    test_cards_total: number;
    test_cards_edited: number;
  };
  locator_verification: {
    pass_rate: number | null;
    generated_total: number;
    role_based: number;
  };
}

function formatMs(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatPct(rate: number | null): string {
  if (rate === null) return "—";
  return `${Math.round(rate * 100)}%`;
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="border border-gray-200 rounded-lg p-4 bg-white">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-xl font-semibold text-gray-900">{value}</div>
      {sub && <div className="text-xs text-gray-400 mt-1">{sub}</div>}
    </div>
  );
}

interface Props {
  tenantId: string;
}

export function CoverageStats({ tenantId }: Props) {
  const { data, isLoading } = useQuery<Metrics>({
    queryKey: ["metrics", tenantId],
    queryFn: () => axios.get(`${API}/metrics/${tenantId}`).then((r) => r.data),
  });

  if (isLoading || !data) return null;

  return (
    <div className="mb-6">
      <h2 className="text-sm font-semibold text-gray-700 mb-3">Product metrics</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat
          label="Median chunk review time"
          value={formatMs(data.review_time.chunk_median_ms)}
        />
        <Stat
          label="Median test-card review time"
          value={formatMs(data.review_time.test_card_median_ms)}
        />
        <Stat
          label="Chunks auto-approved"
          value={formatPct(data.chunk_auto_approval_rate)}
          sub={`${data.chunks_auto_approved} / ${data.chunks_total}`}
        />
        <Stat
          label="Test cards edited before approval"
          value={formatPct(data.human_edits.edit_rate)}
          sub={
            data.human_edits.avg_edits_per_test_card !== null
              ? `avg ${data.human_edits.avg_edits_per_test_card.toFixed(2)} edits/card`
              : undefined
          }
        />
        <Stat
          label="Locator verification pass rate"
          value={formatPct(data.locator_verification.pass_rate)}
          sub={`${data.locator_verification.role_based} / ${data.locator_verification.generated_total} role-based`}
        />
      </div>
    </div>
  );
}
