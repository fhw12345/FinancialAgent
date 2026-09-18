/** Restore sealed evidence navigation from the canonical run, not translated prose. */
import { useQuery } from "@tanstack/react-query";
import { getRunEvidence } from "../../services/evidence";
import { EvidencePanel } from "../portfolio/EvidencePanel";
import { StrategyReceipt } from "../portfolio/StrategyReceipt";
import { getRunStrategy } from "../../services/researchStrategy";
export function RunEvidence({ runId }: { runId: string }) {
  const query = useQuery({
    queryKey: ["run-evidence", runId],
    queryFn: ({ signal }) => getRunEvidence(runId, signal),
    refetchInterval: 5000,
  });
  const strategy = useQuery({
    queryKey: ["run-strategy", runId],
    queryFn: ({ signal }) => getRunStrategy(runId, signal),
    refetchInterval: 5000,
  });
  if (query.error) return <p role="alert">Evidence unavailable / 证据不可用</p>;
  return (
    <>
      {strategy.data && <StrategyReceipt summary={strategy.data} />}{" "}
      {query.data && <EvidencePanel summary={query.data} />}
    </>
  );
}
