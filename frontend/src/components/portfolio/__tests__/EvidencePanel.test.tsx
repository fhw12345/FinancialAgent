import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { EvidencePanel } from "../EvidencePanel";
import {
  getDossier,
  getManifest,
  getEvidence,
  evidenceSummarySchema,
} from "../../../services/evidence";
vi.mock("../../../services/evidence", async () => {
  const original = await vi.importActual<
    typeof import("../../../services/evidence")
  >("../../../services/evidence");
  return {
    ...original,
    getDossier: vi.fn(),
    getManifest: vi.fn(),
    getEvidence: vi.fn(),
  };
});
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ i18n: { language: "en" } }),
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
it("shows only structured matching while source publication remains unknown", async () => {
  vi.mocked(getDossier).mockResolvedValue({
    run_status: "completed",
    dossier: {
      dossier_id: "d",
      snapshot_id: "s",
      manifest_hash: "h",
      run_id: "r",
      symbol: "AAPL",
      errors: [],
      prose_verification: "unverified",
      actionable: false,
      claims: [
        {
          claim_id: "c",
          status: "matches_snapshot",
          reasons: [],
          computed_value: null,
          evidence_ids: ["ev_1"],
          claim: {
            kind: "fact",
            symbol: "AAPL",
            metric: "price.close_reference",
            value: 100,
            unit: "USD",
            period: "session",
            period_end: "2026-09-16",
            evidence_ids: ["ev_1"],
            method: null,
            text: "Untrusted words",
          },
        },
      ],
    },
  });
  vi.mocked(getManifest).mockResolvedValue({
    snapshot_id: "s",
    state: "sealed",
    manifest_hash: "h",
    coverage: { quote: "available" },
    conflicts: {},
    records_count: 1,
  });
  vi.mocked(getEvidence).mockResolvedValue({
    evidence_id: "ev_1",
    snapshot_id: "s",
    symbol: "AAPL",
    instrument_id: "AAPL:USD",
    metric: "price.close_reference",
    value: 100,
    unit: "USD",
    period: "session",
    period_start: null,
    period_end: "2026-09-16",
    observed_at: null,
    published_at: null,
    fetched_at: "2026-09-17",
    provider: "yfinance",
    source_uri: null,
    document_id: null,
    point_in_time_status: "retrieval_only",
    quality: "available",
    payload_hash: "h",
    adapter_version: "idq-004@1",
  });
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <EvidencePanel
        summary={{
          snapshot_ids: ["s"],
          dossier_ids: ["d"],
          errors: [],
          prose_verification: "unverified",
          actionable: false,
        }}
      />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByTestId("open-evidence-dossier"));
  expect(await screen.findByTestId("claim-verification")).toHaveTextContent(
    "not prose verification",
  );
  fireEvent.click(await screen.findByTestId("view-claim-evidence"));
  expect(await screen.findByTestId("evidence-record")).toHaveTextContent(
    "Published: unknown",
  );
  expect(screen.getByTestId("evidence-id")).toHaveTextContent("ev_1");
});
it("rejects an alleged actionable evidence summary", () => {
  expect(
    evidenceSummarySchema.safeParse({
      snapshot_ids: [],
      dossier_ids: [],
      errors: [],
      prose_verification: "verified",
      actionable: true,
    }).success,
  ).toBe(false);
});
