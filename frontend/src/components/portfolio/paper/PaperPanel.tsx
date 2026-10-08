/** Opt-in local manual PAPER journal; opening/selecting only reads stored state. */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getPaper,
  listPaper,
  type PaperView,
} from "../../../services/paperLedger";
import { CreatePaperForm, PaperJournalForm } from "./PaperForms";
import { PaperDetails } from "./PaperDetails";

export function PaperPanel() {
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState("");
  const client = useQueryClient();
  const accounts = useQuery({
    queryKey: ["paper", "accounts"],
    queryFn: ({ signal }) => listPaper(signal),
    enabled: open,
    refetchOnWindowFocus: false,
  });
  const detail = useQuery({
    queryKey: ["paper", "detail", selected],
    queryFn: ({ signal }) => getPaper(selected, signal),
    enabled: open && !!selected,
    refetchOnWindowFocus: false,
  });
  const changed = () => {
    void client.invalidateQueries({ queryKey: ["paper"] });
  };
  const saved = (view: PaperView) => {
    setCreating(false);
    setSelected(view.experiment.experiment_id);
    client.setQueryData(
      ["paper", "detail", view.experiment.experiment_id],
      view,
    );
    changed();
  };
  return (
    <section data-testid="paper-panel" className="space-y-3 border-b p-4">
      <h3 className="font-semibold">
        PAPER · Manual scenario ledger / 人工模拟账本
      </h3>
      <p className="text-sm text-amber-900">
        Independent scenario bookkeeping, not a broker or AI-approved trading
        account. No trades/marks run while offline, no historical fills on
        restart. / 独立人工情景记账，不自动交易；离线不运行，重启不补造成交。
      </p>
      <button
        type="button"
        data-testid="paper-open"
        className="rounded border px-2 py-1"
        onClick={() => setOpen((old) => !old)}
      >
        Open PAPER journal / 打开模拟账本
      </button>
      {open && (
        <>
          <button
            type="button"
            data-testid="paper-new"
            className="ml-2 rounded border px-2 py-1"
            onClick={() => setCreating((old) => !old)}
          >
            New cash-only scenario / 新建纯现金情景
          </button>
          {creating && <CreatePaperForm saved={saved} />}
          <label className="block text-sm">
            Scenario / 情景{" "}
            <select
              value={selected}
              data-testid="paper-account-select"
              className="max-w-full rounded border p-1"
              onChange={(e) => setSelected(e.target.value)}
            >
              <option value="">Select explicitly / 请明确选择</option>
              {accounts.data?.map((account) => (
                <option
                  key={account.experiment_id}
                  value={account.experiment_id}
                >
                  {account.name} {account.closed ? "(closed)" : ""}
                </option>
              ))}
            </select>
          </label>
          {(accounts.isLoading || (selected && detail.isLoading)) && (
            <p role="status">Loading PAPER history / 加载模拟历史…</p>
          )}
          {(accounts.error || detail.error) && (
            <p role="alert">
              PAPER history unavailable; not an empty or zero-risk account. /
              读取失败，不代表空账户或零风险。
            </p>
          )}
          <button
            type="button"
            data-testid="paper-reload"
            onClick={changed}
            className="rounded border px-2 py-1 text-sm"
          >
            Reload stored state (no price fetch) / 重读状态（不取新价）
          </button>
          {detail.data && selected && (
            <>
              <PaperDetails
                key={`detail:${selected}:${detail.data.experiment.sequence}`}
                view={detail.data}
                changed={changed}
              />
              {!detail.data.projection.closed && (
                <PaperJournalForm
                  key={`journal:${selected}:${detail.data.experiment.sequence}`}
                  view={detail.data}
                  changed={changed}
                />
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
