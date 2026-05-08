/**
 * ResearchPanel — render Phase2 structured research blocks (W2.11).
 *
 * Pulls thesis / valuation / price_target / scenarios / catalysts /
 * risks / *_derivation off PortfolioOrder.metadata and renders each
 * present block. Missing blocks are skipped silently — back-compat
 * with pre-W2.7 decisions that have only reasoning.
 *
 * Carries data-testid attributes so e2e can assert which sections
 * rendered without snapshotting the full DOM.
 */
import type { DecisionMetadata } from "../../hooks/useDecisions";

interface ValuationMethod {
  method: string;
  value?: number | null;
  note: string;
}

interface PriceTarget {
  value: number;
  horizon_days: number;
  method?: string | null;
}

interface ScenarioCase {
  price_target: number;
  probability: number;
  rationale: string;
}

interface ScenarioSet {
  bull: ScenarioCase;
  base: ScenarioCase;
  bear: ScenarioCase;
}

interface Catalyst {
  event: string;
  eta_window: string;
}

interface Derivation {
  value: number;
  formula: string;
  inputs: Record<string, unknown>;
}

function ThesisBlock({ thesis }: { thesis: string[] }) {
  return (
    <section data-testid="research-thesis" className="mt-3">
      <h4 className="text-xs font-semibold uppercase text-gray-500 mb-1">
        Thesis
      </h4>
      <ol className="list-decimal list-inside space-y-1 text-sm text-gray-700">
        {thesis.map((b, i) => (
          <li key={i}>{b}</li>
        ))}
      </ol>
    </section>
  );
}

function ValuationBlock({ items }: { items: ValuationMethod[] }) {
  return (
    <section data-testid="research-valuation" className="mt-3">
      <h4 className="text-xs font-semibold uppercase text-gray-500 mb-1">
        Valuation triangulation
      </h4>
      <table className="w-full text-xs">
        <thead className="text-left text-gray-500">
          <tr>
            <th className="pr-3 font-normal">method</th>
            <th className="pr-3 font-normal">value</th>
            <th className="font-normal">note</th>
          </tr>
        </thead>
        <tbody className="text-gray-700">
          {items.map((v, i) => (
            <tr key={i}>
              <td className="pr-3 font-mono">{v.method}</td>
              <td className="pr-3 font-mono">
                {v.value != null ? v.value.toFixed(2) : "—"}
              </td>
              <td>{v.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function ScenariosBlock({ scenarios }: { scenarios: ScenarioSet }) {
  const cases = [
    { label: "Bull", v: scenarios.bull, color: "text-emerald-700" },
    { label: "Base", v: scenarios.base, color: "text-gray-700" },
    { label: "Bear", v: scenarios.bear, color: "text-rose-700" },
  ];
  const probSum =
    scenarios.bull.probability +
    scenarios.base.probability +
    scenarios.bear.probability;
  const probValid = Math.abs(probSum - 1.0) <= 0.02;
  return (
    <section data-testid="research-scenarios" className="mt-3">
      <h4 className="text-xs font-semibold uppercase text-gray-500 mb-1">
        Scenarios{" "}
        {!probValid && (
          <span className="ml-1 text-rose-700 font-normal" data-testid="scenarios-prob-warning">
            (⚠ probability sum {probSum.toFixed(2)} ≠ 1.0)
          </span>
        )}
      </h4>
      <table className="w-full text-xs">
        <thead className="text-left text-gray-500">
          <tr>
            <th className="pr-3 font-normal">case</th>
            <th className="pr-3 font-normal">PT</th>
            <th className="pr-3 font-normal">prob</th>
            <th className="font-normal">rationale</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.label}>
              <td className={`pr-3 font-medium ${c.color}`}>{c.label}</td>
              <td className="pr-3 font-mono text-gray-700">
                ${c.v.price_target.toFixed(2)}
              </td>
              <td className="pr-3 font-mono text-gray-700">
                {(c.v.probability * 100).toFixed(0)}%
              </td>
              <td className="text-gray-700">{c.v.rationale}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function CatalystsBlock({ items }: { items: Catalyst[] }) {
  return (
    <section data-testid="research-catalysts" className="mt-3">
      <h4 className="text-xs font-semibold uppercase text-gray-500 mb-1">
        Catalysts (next 4 weeks)
      </h4>
      <ul className="list-disc list-inside space-y-1 text-sm text-gray-700">
        {items.map((c, i) => (
          <li key={i}>
            <span className="font-medium">{c.event}</span>{" "}
            <span className="text-gray-500">— {c.eta_window}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function RisksBlock({ items }: { items: string[] }) {
  return (
    <section data-testid="research-risks" className="mt-3">
      <h4 className="text-xs font-semibold uppercase text-gray-500 mb-1">
        Risks (ranked)
      </h4>
      <ol className="list-decimal list-inside space-y-1 text-sm text-gray-700">
        {items.map((r, i) => (
          <li key={i}>{r}</li>
        ))}
      </ol>
    </section>
  );
}

function DerivationChip({
  label,
  d,
}: {
  label: string;
  d: Derivation | null | undefined;
}) {
  if (!d) return null;
  const inputsStr = Object.entries(d.inputs)
    .map(([k, v]) => `${k}=${v}`)
    .join(", ");
  return (
    <span
      data-testid={`derivation-${label}`}
      title={`${d.formula}(${inputsStr}) = ${d.value}`}
      className="inline-flex items-center rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-mono text-blue-800 dark:bg-blue-900/30 dark:text-blue-300"
    >
      ƒ {label}
    </span>
  );
}

export function ResearchPanel({ metadata }: { metadata: DecisionMetadata }) {
  const thesis = metadata?.thesis as string[] | null | undefined;
  const valuation = metadata?.valuation as ValuationMethod[] | null | undefined;
  const priceTarget = metadata?.price_target as PriceTarget | null | undefined;
  const scenarios = metadata?.scenarios as ScenarioSet | null | undefined;
  const catalysts = metadata?.catalysts as Catalyst[] | null | undefined;
  const risks = metadata?.risks as string[] | null | undefined;

  const entryD = metadata?.entry_derivation as Derivation | null | undefined;
  const stopD = metadata?.stop_derivation as Derivation | null | undefined;
  const targetD = metadata?.target_derivation as Derivation | null | undefined;
  const sizeD = metadata?.size_derivation as Derivation | null | undefined;

  const anyBlock =
    thesis ||
    valuation ||
    priceTarget ||
    scenarios ||
    catalysts ||
    risks ||
    entryD ||
    stopD ||
    targetD ||
    sizeD;
  if (!anyBlock) return null;

  return (
    <div data-testid="research-panel" className="mt-4 border-t pt-3">
      {(entryD || stopD || targetD || sizeD) && (
        <div className="flex flex-wrap items-center gap-1 mb-3">
          <span className="text-xs uppercase text-gray-500 mr-1">
            Derivations:
          </span>
          <DerivationChip label="entry" d={entryD} />
          <DerivationChip label="stop" d={stopD} />
          <DerivationChip label="target" d={targetD} />
          <DerivationChip label="size" d={sizeD} />
        </div>
      )}
      {thesis && thesis.length > 0 && <ThesisBlock thesis={thesis} />}
      {valuation && valuation.length > 0 && (
        <ValuationBlock items={valuation} />
      )}
      {priceTarget && (
        <section data-testid="research-pt" className="mt-3 text-sm text-gray-700">
          <span className="text-xs font-semibold uppercase text-gray-500 mr-2">
            Price target:
          </span>
          <span className="font-mono">${priceTarget.value.toFixed(2)}</span>
          <span className="text-gray-500">
            {" "}
            · {priceTarget.horizon_days}d
            {priceTarget.method ? ` · ${priceTarget.method}` : ""}
          </span>
        </section>
      )}
      {scenarios && <ScenariosBlock scenarios={scenarios} />}
      {catalysts && catalysts.length > 0 && <CatalystsBlock items={catalysts} />}
      {risks && risks.length > 0 && <RisksBlock items={risks} />}
    </div>
  );
}
