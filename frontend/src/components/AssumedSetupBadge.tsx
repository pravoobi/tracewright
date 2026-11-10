export interface SetupEntry {
  type?: string;
  source?: "document" | "assumed";
  [key: string]: unknown;
}

interface Props {
  tierSources?: { assumed_setup?: number } | null;
  setupManifest?: SetupEntry[] | null;
}

/**
 * Warns that some of a card's setup data (users, codes, products, ...) was
 * chosen by the Planner rather than quoted from the requirements, so the
 * customer must confirm or fulfil it before a generated test can pass.
 * Renders nothing for cards with no assumed entries, and for older cards
 * created before provenance was tracked (field absent = unknown, not "0").
 */
export default function AssumedSetupBadge({ tierSources, setupManifest }: Props) {
  const count = tierSources?.assumed_setup;
  if (typeof count !== "number" || count <= 0) return null;

  const assumed = (setupManifest ?? []).filter((e) => e.source === "assumed");
  const tooltip =
    `${count} setup item${count === 1 ? "" : "s"} not found in your documents — confirm or provide: ` +
    (assumed.map((e) => e.type ?? "item").join(", ") || "see setup manifest");

  return (
    <span
      className="text-xs px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 cursor-help"
      title={tooltip}
    >
      ⚠ {count} assumed setup
    </span>
  );
}
