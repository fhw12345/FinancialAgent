import { useEffect, useRef, useState } from "react";
import { Gauge, Play, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { EvaluationHistory } from "../components/evaluation/EvaluationHistory";
import { LiveEvaluationResults } from "../components/evaluation/LiveEvaluationResults";
import {
  EvaluationRunSummary,
  EvaluationReport,
  getLiveEvaluation,
  getLiveEvaluationCapabilities,
  listLiveEvaluations,
  LiveEvaluationCapabilities,
  LiveEvaluationLane,
  LiveEvaluationReport,
  runEvaluation,
  startLiveEvaluation,
} from "../services/evaluations";

function percentage(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export default function EvaluationPage() {
  const { t } = useTranslation("evaluation");
  const [report, setReport] = useState<EvaluationReport | null>(null);
  const [liveReport, setLiveReport] = useState<LiveEvaluationReport | null>(
    null,
  );
  const [history, setHistory] = useState<EvaluationRunSummary[]>([]);
  const [mode, setMode] = useState<"deterministic" | "live">("deterministic");
  const [liveLane, setLiveLane] =
    useState<LiveEvaluationLane>("replay_live");
  const [capabilities, setCapabilities] =
    useState<LiveEvaluationCapabilities>({
      fake_live_available: false,
      provider_smoke_available: false,
    });
  const [maxCostUsd, setMaxCostUsd] = useState(0.25);
  const [caseLimit, setCaseLimit] = useState(8);
  const [liveConsent, setLiveConsent] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const pollControllerRef = useRef<AbortController | null>(null);

  const refreshHistory = async () => {
    try {
      setHistory(await listLiveEvaluations());
      setHistoryError(null);
    } catch {
      setHistoryError(t("live.historyError"));
    }
  };

  useEffect(() => {
    void refreshHistory();
    void getLiveEvaluationCapabilities()
      .then((available) => {
        setCapabilities(available);
        if (
          available.fake_live_available &&
          new URLSearchParams(window.location.search).has("evalFake")
        ) {
          setLiveLane("fake_live");
        }
      })
      .catch(() => setHistoryError(t("live.capabilitiesError")));
    return () => pollControllerRef.current?.abort();
  }, []);

  const pollLiveRun = async (runId: string) => {
    pollControllerRef.current?.abort();
    const controller = new AbortController();
    pollControllerRef.current = controller;
    for (;;) {
      const current = await getLiveEvaluation(runId, controller.signal);
      setLiveReport(current);
      if (current.status !== "running") return current;
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
    }
  };

  const handleRun = async () => {
    setIsRunning(true);
    setError(null);
    try {
      if (mode === "deterministic") {
        setReport(await runEvaluation());
        setLiveReport(null);
      } else {
        if (!liveConsent) {
          throw new Error(t("live.consentRequired"));
        }
        if (!Number.isFinite(maxCostUsd) || maxCostUsd <= 0 || maxCostUsd > 25) {
          throw new Error(t("live.invalidBudget"));
        }
        if (
          !Number.isInteger(caseLimit) ||
          caseLimit < 1 ||
          caseLimit > 20
        ) {
          throw new Error(t("live.invalidCaseLimit"));
        }
        const started = await startLiveEvaluation({
          lane: liveLane,
          enabled: true,
          max_cost_usd: maxCostUsd,
          case_limit: caseLimit,
        });
        setReport(null);
        await pollLiveRun(started.run_id);
        await refreshHistory();
      }
    } catch (caught) {
      if (
        caught instanceof Error &&
        ["AbortError", "CanceledError"].includes(caught.name)
      ) {
        return;
      }
      setError(caught instanceof Error ? caught.message : t("runError"));
    } finally {
      setIsRunning(false);
    }
  };

  const handleSelectHistory = async (runId: string) => {
    setMode("live");
    setError(null);
    setIsRunning(true);
    try {
      await pollLiveRun(runId);
    } catch (caught) {
      if (
        caught instanceof Error &&
        ["AbortError", "CanceledError"].includes(caught.name)
      ) {
        return;
      }
      setError(t("live.selectionError"));
    } finally {
      setIsRunning(false);
    }
  };

  const failures = report?.results.filter((result) => !result.passed) ?? [];

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{t("title")}</h1>
            <p className="mt-1 text-sm text-gray-500">{t("description")}</p>
          </div>
          <button
            type="button"
            data-testid="run-evaluation"
            onClick={() => void handleRun()}
            disabled={isRunning}
            className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Play className="h-4 w-4" />
            {isRunning ? t("running") : t("run")}
          </button>
        </div>

        <section className="rounded-xl bg-white p-5 shadow">
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="evaluation-mode"
                checked={mode === "deterministic"}
                onChange={() => setMode("deterministic")}
              />
              {t("modes.deterministic")}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                data-testid="evaluation-mode-live"
                type="radio"
                name="evaluation-mode"
                checked={mode === "live"}
                onChange={() => setMode("live")}
              />
              {t("modes.live")}
            </label>
          </div>

          {mode === "live" && (
            <div className="mt-5 grid gap-4 md:grid-cols-4">
              <label className="text-sm text-gray-700">
                {t("live.lane")}
                <select
                  data-testid="live-evaluation-lane"
                  value={liveLane}
                  onChange={(event) =>
                    setLiveLane(event.target.value as LiveEvaluationLane)
                  }
                  className="mt-1 block w-full rounded border border-gray-300 px-3 py-2"
                >
                  <option value="replay_live">{t("live.replay")}</option>
                  {capabilities.provider_smoke_available && (
                    <option value="provider_smoke">{t("live.smoke")}</option>
                  )}
                  {capabilities.fake_live_available && (
                    <option value="fake_live">{t("live.fake")}</option>
                  )}
                </select>
              </label>
              <label className="text-sm text-gray-700">
                {t("live.budget")}
                <input
                  data-testid="live-evaluation-budget"
                  type="number"
                  min="0.000001"
                  max="25"
                  step="0.01"
                  value={maxCostUsd}
                  onChange={(event) =>
                    setMaxCostUsd(Number(event.target.value))
                  }
                  className="mt-1 block w-full rounded border border-gray-300 px-3 py-2"
                />
              </label>
              <label className="text-sm text-gray-700">
                {t("live.caseLimit")}
                <input
                  data-testid="live-evaluation-case-limit"
                  type="number"
                  min="1"
                  max="20"
                  value={caseLimit}
                  onChange={(event) => setCaseLimit(Number(event.target.value))}
                  className="mt-1 block w-full rounded border border-gray-300 px-3 py-2"
                />
              </label>
              <label className="flex items-center gap-2 self-end rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm">
                <input
                  data-testid="live-evaluation-consent"
                  type="checkbox"
                  checked={liveConsent}
                  onChange={(event) => setLiveConsent(event.target.checked)}
                />
                {t("live.consent")}
              </label>
            </div>
          )}
        </section>

        {error && (
          <div
            data-testid="evaluation-error"
            className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
          >
            {error}
          </div>
        )}

        {historyError && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            {historyError}
          </div>
        )}

        {!report && !liveReport && !error && (
          <div className="rounded-xl border border-dashed border-gray-300 bg-white p-12 text-center text-gray-500">
            <Gauge className="mx-auto mb-3 h-10 w-10 text-indigo-500" />
            {t("empty")}
          </div>
        )}

        {mode === "live" && liveReport && (
          <LiveEvaluationResults report={liveReport} />
        )}

        {mode === "deterministic" && report && (
          <>
            <div
              data-testid="evaluation-status"
              data-status={report.gates_passed ? "pass" : "fail"}
              className={`flex items-center gap-3 rounded-xl border p-5 ${
                report.gates_passed
                  ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                  : "border-red-200 bg-red-50 text-red-900"
              }`}
            >
              <ShieldCheck className="h-7 w-7" />
              <div>
                <p className="text-lg font-semibold">
                  {report.gates_passed ? t("passed") : t("failed")}
                </p>
                <p className="text-sm">
                  {t("suiteSummary", {
                    suite: report.suite_version,
                    passed: report.passed_cases,
                    total: report.total_cases,
                  })}
                </p>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <MetricCard
                testId="metric-quality"
                label={t("metrics.quality")}
                value={percentage(report.quality_score)}
              />
              <MetricCard
                label={t("metrics.router")}
                value={percentage(report.router_accuracy)}
              />
              <MetricCard
                testId="metric-injection"
                label={t("metrics.injection")}
                value={percentage(report.prompt_injection_safety)}
              />
              <MetricCard
                label={t("metrics.cost")}
                value={percentage(report.cost_policy_compliance)}
              />
              <MetricCard
                label={t("metrics.executionMode")}
                value={percentage(report.execution_mode_accuracy)}
              />
              <MetricCard
                label={t("metrics.unknownSymbol")}
                value={percentage(report.unknown_symbol_safety)}
              />
              <MetricCard
                label={t("metrics.p95Latency")}
                value={`${report.p95_latency_ms.toFixed(1)} ms`}
              />
              <MetricCard
                testId="metric-live-model-calls"
                label={t("metrics.liveCalls")}
                value={String(report.live_model_calls)}
              />
            </div>

            <section className="overflow-hidden rounded-xl bg-white shadow">
              <div className="border-b px-5 py-4">
                <h2 className="font-semibold text-gray-900">{t("gates")}</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left">{t("gate")}</th>
                      <th className="px-4 py-3 text-right">{t("observed")}</th>
                      <th className="px-4 py-3 text-right">
                        {t("requirement")}
                      </th>
                      <th className="px-4 py-3 text-right">{t("result")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {report.gates.map((gate) => (
                      <tr key={gate.gate_id}>
                        <td className="px-4 py-3 font-mono">{gate.gate_id}</td>
                        <td className="px-4 py-3 text-right">
                          {gate.observed.toFixed(3)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          {gate.operator} {gate.threshold}
                        </td>
                        <td
                          className={`px-4 py-3 text-right font-semibold ${
                            gate.passed ? "text-emerald-600" : "text-red-600"
                          }`}
                        >
                          {gate.passed ? "PASS" : "FAIL"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <div className="grid gap-6 lg:grid-cols-3">
              <VersionList
                title={t("usedPromptVersions")}
                values={report.used_prompt_versions}
                emptyValue={t("live.results.none")}
              />
              <VersionList
                title={t("configuredPromptVersions")}
                values={report.configured_prompt_versions}
                emptyValue={t("live.results.none")}
              />
              <VersionList
                title={t("modelRoutes")}
                values={report.evaluated_model_routes}
                emptyValue={t("live.results.none")}
              />
            </div>

            <section className="rounded-xl bg-white p-5 shadow">
              <h2 className="font-semibold text-gray-900">{t("failures")}</h2>
              {failures.length === 0 ? (
                <p className="mt-3 text-sm text-emerald-600">
                  {t("noFailures")}
                </p>
              ) : (
                <ul className="mt-3 space-y-2 text-sm">
                  {failures.slice(0, 12).map((failure) => (
                    <li key={failure.case_id} className="rounded bg-gray-50 p-3">
                      <span className="font-mono font-semibold">
                        {failure.case_id}
                      </span>
                      <span className="ml-2 text-gray-600">
                        {failure.failures.join("; ")}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}

        <EvaluationHistory
          runs={history}
          onSelect={(runId) => void handleSelectHistory(runId)}
        />
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  testId,
}: {
  label: string;
  value: string;
  testId?: string;
}) {
  return (
    <div data-testid={testId} className="rounded-xl bg-white p-5 shadow">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-gray-900">{value}</p>
    </div>
  );
}

function VersionList({
  title,
  values,
  emptyValue,
}: {
  title: string;
  values: Record<string, string>;
  emptyValue: string;
}) {
  return (
    <section className="rounded-xl bg-white p-5 shadow">
      <h2 className="font-semibold text-gray-900">{title}</h2>
      <dl className="mt-3 space-y-2 text-sm">
        {Object.keys(values).length === 0 ? (
          <p className="text-gray-500">{emptyValue}</p>
        ) : (
          Object.entries(values).map(([name, version]) => (
            <div
              key={name}
              className="flex items-center justify-between gap-4 rounded bg-gray-50 px-3 py-2"
            >
              <dt className="font-mono text-gray-700">{name}</dt>
              <dd className="font-mono text-indigo-700">{version}</dd>
            </div>
          ))
        )}
      </dl>
    </section>
  );
}
