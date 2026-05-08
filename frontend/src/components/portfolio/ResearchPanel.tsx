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
 *
 * W3.7 footnote rendering: thesis bullets that the W3.6 prompt
 * teaches the LLM to write end with bracketed source-ID tokens like
 * `[FH-Q-AAPL-2026-05-09]` / `[AV-OV-NVDA-2025-09-30]`. We extract
 * those tokens, replace each with a numeric superscript chip, and
 * render the unique-id list at the bottom of the panel.
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

// W3.7 footnote token shape: `[PREFIX-FIELD-SYMBOL-YYYY-MM-DD]`.
// PREFIX ∈ {FH, YF, AV, plus any uppercase fallback the backend emits};
// FIELD ∈ {Q, OV, CF, BS, EAR, INS, N}. We're permissive on the first
// two segments (uppercase letters/digits/underscore) so a future
// provider doesn't silently fall through this regex.
export const SOURCE_ID_PATTERN = /\[([A-Z][A-Z0-9_]*-[A-Z]+-[A-Z0-9.]+-\d{4}-\d{2}-\d{2})\]/g;

interface ParsedThesisBullet {
  segments: Array<
    | { kind: "text"; value: string }
    | { kind: "ref"; id: string; index: number }
  >;
}

export interface ExtractedFootnotes {
  bullets: ParsedThesisBullet[];
  ids: string[]; // unique, in first-citation order
}

export function extractFootnotes(thesis: readonly string[]): ExtractedFootnotes {
  const ids: string[] = [];
  const indexById = new Map<string, number>();
  const bullets: ParsedThesisBullet[] = thesis.map((bullet) => {
    const segments: ParsedThesisBullet["segments"] = [];
    let cursor = 0;
    SOURCE_ID_PATTERN.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = SOURCE_ID_PATTERN.exec(bullet)) !== null) {
      if (match.index > cursor) {
        segments.push({ kind: "text", value: bullet.slice(cursor, match.index) });
      }
      const id = match[1];
      let i = indexById.get(id);
      if (i === undefined) {
        i = ids.length + 1; // 1-based superscript number
        indexById.set(id, i);
        ids.push(id);
      }
      segments.push({ kind: "ref", id, index: i });
      cursor = match.index + match[0].length;
    }
    if (cursor < bullet.length) {
      segments.push({ kind: "text", value: bullet.slice(cursor) });
    }
    if (segments.length === 0) {
      // Defensive — empty bullet still renders a row.
      segments.push({ kind: "text", value: "" });
    }
    return { segments };
  });
  return { bullets, ids };
}

// W3.7 source-ID parsing for the bottom list. The backend builds IDs
// via `{PREFIX}-{FIELD}-{SYMBOL}-{YYYY-MM-DD}`; we only need the human
// label for the chip — provider name + field code + asof date.
const PROVIDER_LABEL: Record<string, string> = {
  FH: "Finnhub",
  AV: "Alpha Vantage",
  YF: "yfinance",
};
const FIELD_LABEL: Record<string, string> = {
  Q: "quote",
  OV: "company overview",
  CF: "cash flow",
  BS: "balance sheet",
  EAR: "earnings",
  INS: "insider",
  N: "news",
};

export interface SourceIdParts {
  provider: string;
  field: string;
  symbol: string;
  asof: string;
}

export function parseSourceId(id: string): SourceIdParts | null {
  // Walk from right: trailing YYYY-MM-DD, then symbol, then field,
  // then provider. The symbol is the only segment that can carry a
  // dot (BRK.B etc) so the simplest approach is split + reassemble.
  const parts = id.split("-");
  if (parts.length < 5) return null;
  const asof = parts.slice(-3).join("-");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(asof)) return null;
  const head = parts.slice(0, -3);
  if (head.length < 3) return null;
  const [provider, field, ...symbolParts] = head;
  return {
    provider,
    field,
    symbol: symbolParts.join("-"),
    asof,
  };
}

function FootnoteChip({ index, id }: { index: number; id: string }) {
  const parsed = parseSourceId(id);
  const title = parsed
    ? `${PROVIDER_LABEL[parsed.provider] ?? parsed.provider} · ${
        FIELD_LABEL[parsed.field] ?? parsed.field
      } · ${parsed.symbol} · asof ${parsed.asof}`
    : id;
  return (
    <sup
      data-testid={`footnote-ref-${index}`}
      title={title}
      className="ml-0.5 inline-flex items-center rounded bg-blue-50 px-1 text-[10px] font-mono text-blue-800 dark:bg-blue-900/30 dark:text-blue-300"
    >
      [{index}]
    </sup>
  );
}

function ThesisBlock({ bullets }: { bullets: ParsedThesisBullet[] }) {
  return (
    <section data-testid="research-thesis" className="mt-3">
      <h4 className="text-xs font-semibold uppercase text-gray-500 mb-1">
        Thesis
      </h4>
      <ol className="list-decimal list-inside space-y-1 text-sm text-gray-700">
        {bullets.map((b, i) => (
          <li key={i}>
            {b.segments.map((seg, j) =>
              seg.kind === "text" ? (
                <span key={j}>{seg.value}</span>
              ) : (
                <FootnoteChip key={j} index={seg.index} id={seg.id} />
              ),
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

function FootnoteList({ ids }: { ids: string[] }) {
  if (ids.length === 0) return null;
  return (
    <section data-testid="footnote-list" className="mt-4 border-t pt-2">
      <h4 className="text-xs font-semibold uppercase text-gray-500 mb-1">
        Sources
      </h4>
      <ol className="list-decimal list-inside space-y-0.5 text-xs text-gray-600 font-mono">
        {ids.map((id, i) => {
          const parsed = parseSourceId(id);
          const label = parsed
            ? `${PROVIDER_LABEL[parsed.provider] ?? parsed.provider} · ${
                FIELD_LABEL[parsed.field] ?? parsed.field
              } · ${parsed.symbol} · asof ${parsed.asof}`
            : id;
          return (
            <li key={id} data-testid={`footnote-item-${i + 1}`}>
              [{id}] {label}
            </li>
          );
        })}
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

  const footnotes =
    thesis && thesis.length > 0 ? extractFootnotes(thesis) : null;

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
      {footnotes && footnotes.bullets.length > 0 && (
        <ThesisBlock bullets={footnotes.bullets} />
      )}
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
      {footnotes && footnotes.ids.length > 0 && <FootnoteList ids={footnotes.ids} />}
    </div>
  );
}
