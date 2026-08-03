import { useState } from "react";
import { Gauge, Play, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  EvaluationReport,
  runEvaluation,
} from "../services/evaluations";

function percentage(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export default function EvaluationPage() {
  const { t } = useTranslation("evaluation");
  const [report, setReport] = useState<EvaluationReport | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRun = async () => {
    setIsRunning(true);
    setError(null);
    try {
      setReport(await runEvaluation());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("runError"));
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

        {error && (
          <div
            data-testid="evaluation-error"
            className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
          >
            {error}
          </div>
        )}

        {!report && !error && (
          <div className="rounded-xl border border-dashed border-gray-300 bg-white p-12 text-center text-gray-500">
            <Gauge className="mx-auto mb-3 h-10 w-10 text-indigo-500" />
            {t("empty")}
          </div>
        )}

        {report && (
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

            <div className="grid gap-6 lg:grid-cols-2">
              <VersionList
                title={t("promptVersions")}
                values={report.evaluated_prompt_versions}
              />
              <VersionList
                title={t("modelRoutes")}
                values={report.evaluated_model_routes}
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
}: {
  title: string;
  values: Record<string, string>;
}) {
  return (
    <section className="rounded-xl bg-white p-5 shadow">
      <h2 className="font-semibold text-gray-900">{title}</h2>
      <dl className="mt-3 space-y-2 text-sm">
        {Object.entries(values).map(([name, version]) => (
          <div
            key={name}
            className="flex items-center justify-between gap-4 rounded bg-gray-50 px-3 py-2"
          >
            <dt className="font-mono text-gray-700">{name}</dt>
            <dd className="font-mono text-indigo-700">{version}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
