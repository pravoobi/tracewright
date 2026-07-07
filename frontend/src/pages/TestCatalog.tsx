import { useQuery } from "@tanstack/react-query";
import axios from "axios";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";
const TENANT_ID = import.meta.env.VITE_TENANT_ID || "default-tenant";

interface TestCard {
  id: string;
  test_id: string;
  title: string;
  priority: string;
  test_type: string;
  approval_status: string;
  introduced_in_version: string;
}

const STATUS_COLORS: Record<string, string> = {
  approved: "bg-green-100 text-green-800",
  pending: "bg-yellow-100 text-yellow-800",
  rejected: "bg-red-100 text-red-800",
  needs_clarification: "bg-purple-100 text-purple-800",
};

export function TestCatalog() {
  const { data: cards = [], isLoading } = useQuery<TestCard[]>({
    queryKey: ["test-cards-all", TENANT_ID],
    queryFn: () =>
      axios.get(`${API}/plans/${TENANT_ID}/cards`).then((r) => r.data),
  });

  if (isLoading) return <div className="p-8 text-gray-500">Loading…</div>;

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">
        Test Catalog
        <span className="ml-2 text-base font-normal text-gray-400">
          ({cards.length} total)
        </span>
      </h1>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b bg-gray-50">
            <th className="text-left px-3 py-2 font-medium text-gray-600">ID</th>
            <th className="text-left px-3 py-2 font-medium text-gray-600">Title</th>
            <th className="text-left px-3 py-2 font-medium text-gray-600">Priority</th>
            <th className="text-left px-3 py-2 font-medium text-gray-600">Type</th>
            <th className="text-left px-3 py-2 font-medium text-gray-600">Status</th>
            <th className="text-left px-3 py-2 font-medium text-gray-600">Version</th>
          </tr>
        </thead>
        <tbody>
          {cards.map((card) => (
            <tr key={card.id} className="border-b hover:bg-gray-50">
              <td className="px-3 py-2 font-mono text-xs text-gray-500">{card.test_id}</td>
              <td className="px-3 py-2 text-gray-900">{card.title}</td>
              <td className="px-3 py-2">{card.priority}</td>
              <td className="px-3 py-2 text-gray-500">{card.test_type}</td>
              <td className="px-3 py-2">
                <span
                  className={`text-xs px-2 py-0.5 rounded font-medium ${
                    STATUS_COLORS[card.approval_status] || "bg-gray-100 text-gray-700"
                  }`}
                >
                  {card.approval_status}
                </span>
              </td>
              <td className="px-3 py-2 text-gray-400 text-xs">v{card.introduced_in_version}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {cards.length === 0 && (
        <div className="text-center py-12 text-gray-400">No test cards yet.</div>
      )}
    </div>
  );
}
