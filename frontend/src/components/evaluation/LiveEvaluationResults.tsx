import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  LiveCaseResult,
  LiveEvaluationReport,
} from "../../services/evaluations";

function percentage(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function LiveEvaluationResults({
  report,
}: {
  report: LiveEvaluationReport;
}) {
  const { t } = useTranslation("evaluation");
  const successful = report.gates_passed && report.status === "completed";
  const statusClass = successful
    ? "border-emerald-200 bg-emerald-50 text-emerald-900"
    : report.status === "failed"
      ? "border-red-200 bg-red-50 text-red-900"
      : "border-amber-200 bg-amber-50 text-amber-900";
  const statusLabel = t(`live.statuses.${report.status}`, {
    defaultValue: report.status,
  });

  return (
    <div className="space-y-6">
      <div
        data-testid="live-evaluation-status"
        data-status={report.status}
        className={`flex items-center gap-3 rounded-xl border p-5 ${statusClass}`}
      >
        {successful ? (
          <CheckCircle2 className="h-7 w-7" />
        ) : (
          <AlertTriangle className="h-7 w-7" />
        )}
        <div>
          <p className="text-lg font-semibold">
            {successful
              ? t("live.results.gatesPassed")
              : `${t("modes.live")} ${statusLabel}`}
          </p>
          <p className="text-sm">
            {t("live.results.summary", {
              lane: report.lane,
              passRate: percentage(report.metrics.case_pass_rate),
              cost: report.metrics.estimated_cost_usd.toFixed(6),
              budget: report.max_cost_usd.toFixed(4),
            })}
          </p>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          testId="live-case-pass-rate"
          label={t("live.results.casePassRate")}
          value={percentage(report.metrics.case_pass_rate)}
        />
        <Metric
          testId="live-tool-recall"
          label={t("live.results.toolRecall")}
          value={percentage(report.metrics.tool_recall)}
        />
        <Metric
          label={t("live.results.toolPrecision")}
          value={percentage(report.metrics.tool_precision)}
        />
        <Metric
          testId="live-judge-quality"
          label={t("live.results.judgeQuality")}
          value={percentage(report.metrics.judge_quality)}
        />
        <Metric
          label={t("live.results.deterministicQuality")}
          value={percentage(report.metrics.deterministic_quality)}
        />
        <Metric
          label={t("live.results.requiredFacts")}
          value={percentage(report.metrics.required_fact_coverage)}
        />
        <Metric
          label={t("live.results.unsupportedClaims")}
          value={percentage(report.metrics.unsupported_claim_rate)}
        />
        <Metric
          label={t("live.results.latency")}
          value={`${report.metrics.p95_latency_ms.toFixed(1)} ms`}
        />
        <Metric
          label={t("live.results.tokens")}
          value={`${report.metrics.input_tokens} / ${report.metrics.output_tokens}`}
        />
        <Metric
          testId="live-estimated-cost"
          label={t("live.results.estimatedCost")}
          value={`$${report.metrics.estimated_cost_usd.toFixed(6)}`}
        />
        <Metric
          testId="live-pricing-catalog"
          label={t("live.results.pricingCatalog")}
          value={report.pricing_catalog_version}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <VersionList
          title={t("live.results.usedPrompts")}
          values={report.used_prompt_versions}
          emptyValue={t("live.results.none")}
        />
        <VersionList
          title={t("live.results.modelRoutes")}
          values={report.model_routes}
          emptyValue={t("live.results.none")}
        />
      </div>

      <section className="rounded-xl bg-white p-5 shadow">
        <h2 className="font-semibold text-gray-900">
          {t("live.results.caseEvidence")}
        </h2>
        <div className="mt-4 space-y-3">
          {report.results.map((result) => (
            <CaseEvidence key={result.case_id} result={result} />
          ))}
        </div>
      </section>
    </div>
  );
}

function CaseEvidence({ result }: { result: LiveCaseResult }) {
  const { t } = useTranslation("evaluation");
  return (
    <details
      data-testid={`live-case-${result.case_id}`}
      data-status={result.status}
      className="rounded-lg border border-gray-200 bg-gray-50 p-4"
    >
      <summary className="cursor-pointer font-mono text-sm font-semibold">
        {result.case_id} ·{" "}
        {t(`live.statuses.${result.status}`, {
          defaultValue: result.status,
        })}{" "}
        · ${result.cost_usd.toFixed(6)}
      </summary>
      <div className="mt-3 space-y-4 text-sm">
        <div className="grid gap-2 md:grid-cols-2">
          <p>
            <strong>{t("live.results.flow")}:</strong>{" "}
            {result.observed_flow ?? t("live.results.none")} /{" "}
            {result.expected_flow}
          </p>
          <p>
            <strong>{t("live.results.promptVersions")}:</strong>{" "}
            {Object.values(result.prompt_versions).join(", ") ||
              t("live.results.none")}
          </p>
          <p>
            <strong>{t("live.results.tools")}:</strong>{" "}
            {result.tools.map((tool) => tool.tool_name).join(", ") ||
              t("live.results.none")}
          </p>
          <p>
            <strong>{t("live.results.scores")}:</strong>{" "}
            {result.deterministic_rubric?.score.toFixed(3) ??
              t("live.results.none")}{" "}
            / {result.judge?.overall_score.toFixed(3) ?? t("live.results.none")}
          </p>
        </div>

        {result.failures.length > 0 && (
          <div className="rounded border border-red-200 bg-red-50 p-3 text-red-700">
            {result.failures.join("; ")}
          </div>
        )}

        <EvidenceTable result={result} />

        <div>
          <h3 className="font-semibold text-gray-900">
            {t("live.results.criteria")}
          </h3>
          {result.deterministic_rubric ? (
            <div className="mt-2 overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 bg-white">
                <thead>
                  <tr>
                    <th className="px-3 py-2 text-left">
                      {t("live.results.criterion")}
                    </th>
                    <th className="px-3 py-2 text-right">
                      {t("live.results.score")}
                    </th>
                    <th className="px-3 py-2 text-left">
                      {t("live.results.evidence")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {result.deterministic_rubric.criteria.map((criterion) => (
                    <tr key={criterion.criterion}>
                      <td className="px-3 py-2 font-mono">
                        {criterion.criterion}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {criterion.score.toFixed(3)}
                      </td>
                      <td className="px-3 py-2">{criterion.evidence}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="mt-2 text-gray-500">{t("live.results.none")}</p>
          )}
        </div>

        {result.judge && result.judge.failures.length > 0 && (
          <div>
            <h3 className="font-semibold text-gray-900">
              {t("live.results.judgeFailures")}
            </h3>
            <ul className="mt-2 space-y-2">
              {result.judge.failures.map((failure) => (
                <li
                  key={`${failure.criterion}-${failure.quote}`}
                  className="rounded bg-white p-3"
                >
                  <p className="font-mono">{failure.criterion}</p>
                  <p>
                    <strong>{t("live.results.reason")}:</strong>{" "}
                    {failure.reason}
                  </p>
                  <p>
                    <strong>{t("live.results.quote")}:</strong> {failure.quote}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="rounded bg-white p-3 text-gray-700">
          {result.final_answer || t("live.results.noAnswer")}
        </div>
      </div>
    </details>
  );
}

function EvidenceTable({ result }: { result: LiveCaseResult }) {
  const { t } = useTranslation("evaluation");
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <div>
        <h3 className="font-semibold text-gray-900">
          {t("live.results.toolEvidence")}
        </h3>
        {result.tools.length === 0 ? (
          <p className="mt-2 text-gray-500">{t("live.results.none")}</p>
        ) : (
          <div className="mt-2 space-y-2">
            {result.tools.map((tool, index) => (
              <div
                key={`${tool.tool_name}-${index}`}
                className="rounded bg-white p-3"
              >
                <p className="font-mono font-semibold">{tool.tool_name}</p>
                <p data-testid="live-tool-source">
                  {t("live.results.source")}:{" "}
                  {tool.source_id ?? t("live.results.none")} ·{" "}
                  {t("live.results.provider")}:{" "}
                  {tool.provider ?? t("live.results.none")}
                </p>
                <p>
                  {t("live.results.duration")}: {tool.duration_ms.toFixed(1)} ms ·{" "}
                  {t("live.results.status")}:{" "}
                  {tool.success
                    ? t("live.statuses.completed")
                    : t("live.statuses.failed")}
                </p>
                <p className="break-all">
                  {t("live.results.arguments")}:{" "}
                  {JSON.stringify(tool.arguments)}
                </p>
                <p className="mt-1 whitespace-pre-wrap">
                  {t("live.results.output")}: {tool.output}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h3 className="font-semibold text-gray-900">
          {t("live.results.modelUsage")}
        </h3>
        {result.model_usages.length === 0 ? (
          <p className="mt-2 text-gray-500">{t("live.results.none")}</p>
        ) : (
          <div className="mt-2 overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 bg-white">
              <thead>
                <tr>
                  <th className="px-3 py-2 text-left">
                    {t("live.results.role")}
                  </th>
                  <th className="px-3 py-2 text-left">
                    {t("live.results.model")}
                  </th>
                  <th className="px-3 py-2 text-right">
                    {t("live.results.inputOutputTokens")}
                  </th>
                  <th className="px-3 py-2 text-right">
                    {t("live.results.cost")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {result.model_usages.map((usage, index) => (
                  <tr
                    key={`${usage.role}-${usage.model}-${index}`}
                    data-testid="live-model-usage"
                  >
                    <td className="px-3 py-2 font-mono">{usage.role}</td>
                    <td className="px-3 py-2">
                      {usage.provider}:{usage.model}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {usage.input_tokens} / {usage.output_tokens}
                    </td>
                    <td className="px-3 py-2 text-right">
                      ${usage.cost_usd.toFixed(6)}
                      <span className="block text-xs text-gray-500">
                        {usage.cost_source}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function Metric({
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
              className="flex justify-between gap-4 rounded bg-gray-50 px-3 py-2"
            >
              <dt className="font-mono">{name}</dt>
              <dd className="font-mono text-indigo-700">{version}</dd>
            </div>
          ))
        )}
      </dl>
    </section>
  );
}
