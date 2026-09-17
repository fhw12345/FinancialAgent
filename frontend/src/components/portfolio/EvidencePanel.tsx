/** Sealed evidence navigation. Labels may translate; IDs, numeric values and units never do. */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  getDossier,
  getManifest,
  getEvidence,
  type EvidenceSummary,
  type EvidenceRecord,
} from "../../services/evidence";
function EvidenceCard({ record }: { record: EvidenceRecord }) {
  return (
    <article
      className="my-3 rounded border p-3 text-sm"
      data-testid="evidence-record"
    >
      <strong>
        {record.symbol} · {record.metric}: {String(record.value)} {record.unit}
      </strong>
      <p className="break-all" data-testid="evidence-id">
        {record.evidence_id}
      </p>
      <p>
        Provider: {record.provider} · Quality: {record.quality}
      </p>
      <p>
        Period: {record.period} · {record.period_start ?? "unknown"} →{" "}
        {record.period_end ?? "unknown"}
      </p>
      <p>
        Observed: {record.observed_at ?? "unknown"} · Published:{" "}
        {record.published_at ?? "unknown"}
      </p>
      <p>
        Retrieved: {record.fetched_at} · PIT: {record.point_in_time_status}
      </p>
      <p>
        Document: {record.document_id ?? "unknown"} · Adapter:{" "}
        {record.adapter_version}
      </p>
      <p className="break-all">Hash: {record.payload_hash}</p>
      {record.source_uri?.startsWith("https://") && (
        <a
          href={record.source_uri}
          target="_blank"
          rel="noopener noreferrer"
          className="underline text-blue-700"
        >
          Source / 来源
        </a>
      )}
    </article>
  );
}
function DossierView({ id }: { id: string }) {
  const { i18n } = useTranslation();
  const zh = i18n.language.startsWith("zh");
  const dossier = useQuery({
    queryKey: ["dossier", id],
    queryFn: ({ signal }) => getDossier(id, signal),
  });
  const snapshot = dossier.data?.dossier.snapshot_id;
  const manifest = useQuery({
    queryKey: ["manifest", snapshot],
    queryFn: ({ signal }) => getManifest(snapshot ?? "", signal),
    enabled: !!snapshot,
  });
  const [selected, setSelected] = useState<string[]>([]);
  const records = useQuery({
    queryKey: ["claim-records", snapshot, selected],
    queryFn: ({ signal }) =>
      Promise.all(selected.map((e) => getEvidence(e, snapshot ?? "", signal))),
    enabled: !!snapshot && selected.length > 0,
  });
  if (dossier.isLoading) return <p role="status">Loading…</p>;
  if (dossier.error)
    return <p role="alert">Dossier unavailable / 证据档案不可用</p>;
  return (
    <div className="space-y-2">
      <p className="text-amber-900">
        {zh
          ? "仅校验结构化字段与封存记录是否匹配；自由文本、投资推论和来源本身的真实性未被自动证明。"
          : "Only structured fields are compared with sealed records. Free prose, investment conclusions and source truth are not automatically verified."}
      </p>
      <p>
        Run: {dossier.data?.run_status ?? "unknown"} ·{" "}
        {dossier.data?.dossier.symbol}
      </p>
      <p className="break-all" data-testid="evidence-snapshot-id">
        {snapshot}
      </p>
      <p>
        {Object.entries(manifest.data?.coverage ?? {})
          .map(([family, state]) => `${family}: ${state}`)
          .join(" · ")}
      </p>
      {dossier.data?.dossier.errors.map((e) => (
        <p key={e} role="status" className="text-red-700">
          {e}
        </p>
      ))}
      {dossier.data?.dossier.claims.map((c) => (
        <div
          key={c.claim_id}
          data-testid="research-claim"
          className="rounded border p-2"
        >
          <p>
            {c.claim.symbol} · {c.claim.metric}:{" "}
            <span data-testid="claim-value">
              {String(c.claim.value)} {c.claim.unit}
            </span>{" "}
            · {c.claim.period} {c.claim.period_end}
          </p>
          <p data-testid="claim-verification">
            {c.status === "matches_snapshot"
              ? zh
                ? "字段匹配（非全文认证）"
                : "Fields match (not prose verification)"
              : c.status}
            : {c.reasons.join(", ")}
          </p>
          <button
            className="rounded border px-2 py-1"
            data-testid="view-claim-evidence"
            disabled={!manifest.data}
            onClick={() => {
              const conflicts = Object.values(manifest.data?.conflicts ?? {})
                .filter((ids) => ids.some((e) => c.evidence_ids.includes(e)))
                .flat();
              setSelected(
                [...new Set([...c.evidence_ids, ...conflicts])].slice(0, 10),
              );
            }}
          >
            {zh ? "查看来源/单位/日期" : "Inspect sources / units / dates"}
          </button>
        </div>
      ))}
      {(manifest.error || records.error) && (
        <p role="alert">Evidence unavailable; no verification implied.</p>
      )}
      {records.isFetching && selected.length > 0 && (
        <p role="status">Loading evidence…</p>
      )}
      {records.data?.map((record) => (
        <EvidenceCard key={record.evidence_id} record={record} />
      ))}
    </div>
  );
}
export function EvidencePanel({ summary }: { summary: EvidenceSummary }) {
  const [selected, setSelected] = useState<string | null>(null);
  const { i18n } = useTranslation();
  const zh = i18n.language.startsWith("zh");
  return (
    <section className="my-2 border-t pt-2" data-testid="evidence-summary">
      <p className="font-semibold">
        {zh ? "封存证据与主张校验" : "Sealed evidence and claim checks"}
      </p>
      <p className="text-xs text-amber-900">
        {zh
          ? "不可批准/不可执行；缺少字段或来源冲突不能由翻译抹掉。"
          : "No approval/execution. Translation cannot remove missing-data or conflict status."}
      </p>
      {summary.errors.map((e) => (
        <p key={e} className="text-red-700 text-xs">
          {e}
        </p>
      ))}
      {summary.dossier_ids.map((id, index) => (
        <button
          key={id}
          data-testid="open-evidence-dossier"
          className="m-1 rounded border px-2 py-1 text-sm"
          onClick={() => setSelected(id)}
        >
          {zh ? "研究证据" : "Research evidence"} {index + 1}
        </button>
      ))}
      {selected && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
        >
          <div className="max-h-[85vh] w-full max-w-4xl overflow-auto rounded bg-white p-5">
            <button
              className="float-right rounded border px-3 py-1"
              onClick={() => setSelected(null)}
            >
              {zh ? "关闭" : "Close"}
            </button>
            <h3 className="mb-4 font-semibold">
              {zh
                ? "证据档案（非行动性）"
                : "Evidence dossier (non-actionable)"}
            </h3>
            <DossierView key={selected} id={selected} />
          </div>
        </div>
      )}
    </section>
  );
}
