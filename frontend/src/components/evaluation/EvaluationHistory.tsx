import { useTranslation } from "react-i18next";
import type { EvaluationRunSummary } from "../../services/evaluations";

export function EvaluationHistory({
  runs,
  onSelect,
}: {
  runs: EvaluationRunSummary[];
  onSelect: (runId: string) => void;
}) {
  const { t, i18n } = useTranslation("evaluation");

  return (
    <section className="rounded-xl bg-white p-5 shadow">
      <h2 className="font-semibold text-gray-900">
        {t("live.history.title")}
      </h2>
      {runs.length === 0 ? (
        <p className="mt-3 text-sm text-gray-500">
          {t("live.history.empty")}
        </p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead>
              <tr>
                <th className="px-3 py-2 text-left">
                  {t("live.history.run")}
                </th>
                <th className="px-3 py-2 text-left">
                  {t("live.history.lane")}
                </th>
                <th className="px-3 py-2 text-left">
                  {t("live.history.status")}
                </th>
                <th className="px-3 py-2 text-left">
                  {t("live.history.created")}
                </th>
                <th className="px-3 py-2 text-right">
                  {t("live.history.passRate")}
                </th>
                <th className="px-3 py-2 text-right">
                  {t("live.history.cost")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {runs.map((run) => (
                <tr key={run.run_id} className="hover:bg-gray-50">
                  <td className="px-3 py-2 font-mono">
                    <button
                      type="button"
                      data-testid="live-history-run"
                      className="text-indigo-700 hover:underline"
                      onClick={() => onSelect(run.run_id)}
                    >
                      {run.run_id.slice(-12)}
                    </button>
                  </td>
                  <td className="px-3 py-2">{run.lane}</td>
                  <td className="px-3 py-2">
                    {t(`live.statuses.${run.status}`, {
                      defaultValue: run.status,
                    })}
                  </td>
                  <td className="px-3 py-2">
                    {new Intl.DateTimeFormat(i18n.language, {
                      dateStyle: "short",
                      timeStyle: "short",
                    }).format(new Date(run.created_at))}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {(run.case_pass_rate * 100).toFixed(1)}%
                  </td>
                  <td className="px-3 py-2 text-right">
                    ${run.estimated_cost_usd.toFixed(6)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
