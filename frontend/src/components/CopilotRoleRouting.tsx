import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  copilotAction,
  copilotError,
  testCopilot,
  type CopilotStatus,
} from "../services/copilot";

type Props = {
  status: CopilotStatus;
  onStatus: (status: CopilotStatus) => void;
};

export default function CopilotRoleRouting({ status, onStatus }: Props) {
  const { i18n } = useTranslation();
  const zh = i18n.language.startsWith("zh");
  const [draft, setDraft] = useState<Record<string, string>>(() => ({
    ...status.role_models,
  }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tested, setTested] = useState<string | null>(null);
  const active = useRef<AbortController | null>(null);
  const cancel = useCallback(() => active.current?.abort(), []);
  useEffect(() => cancel, [cancel]);
  const dirty =
    JSON.stringify(Object.entries(draft).sort()) !==
    JSON.stringify(Object.entries(status.role_models ?? {}).sort());
  const known = new Set(status.models.map((model) => model.id));
  const preset = status.recommended_role_models ?? {};
  const missing = [...new Set(Object.values(preset))].filter(
    (id) => !known.has(id),
  );

  const run = async (role?: string) => {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setError(null);
    setTested(null);
    try {
      if (role) {
        const model = await testCopilot(controller.signal, { role });
        if (!controller.signal.aborted) setTested(`${role} → ${model}`);
      } else {
        const next = await copilotAction(
          "routing",
          { role_models: draft, expected_revision: status.routing_revision },
          controller.signal,
        );
        if (!controller.signal.aborted) onStatus(next);
      }
    } catch (err) {
      if (!controller.signal.aborted) setError(copilotError(err));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  };

  if (!status.roles || status.routing_revision === undefined) return null;
  return (
    <details
      className="rounded border border-gray-200 p-3"
      data-testid="copilot-routing"
    >
      <summary
        className="cursor-pointer font-medium"
        data-testid="copilot-role-settings"
      >
        {zh ? "按角色配置模型" : "Role-based model routing"} · v
        {status.routing_revision}
      </summary>
      <p className="my-3 text-sm text-gray-600">
        {zh
          ? "仅新运行使用保存后的配置；正在进行的运行保持原映射。同一工具循环不切换模型。默认项继承上方默认模型，MAI 不可选。"
          : "Saved changes affect new runs only. Existing runs and tool loops keep their bindings. Empty overrides inherit the default above; MAI is excluded."}
      </p>
      <div className="mb-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded border px-3 py-2 text-sm disabled:opacity-50"
          disabled={
            busy || missing.length > 0 || Object.keys(preset).length === 0
          }
          onClick={() => {
            setDraft({ ...preset });
            setTested(null);
          }}
          data-testid="copilot-preset"
        >
          {zh
            ? "填入多厂商建议（需保存）"
            : "Fill multi-vendor suggestion (save required)"}
        </button>
        <button
          type="button"
          className="rounded border px-3 py-2 text-sm"
          disabled={busy}
          onClick={() => {
            setDraft({});
            setTested(null);
          }}
          data-testid="copilot-clear-roles"
        >
          {zh
            ? "全部恢复默认（需保存）"
            : "Reset all to default (save required)"}
        </button>
      </div>
      {missing.length > 0 && (
        <p className="mb-3 text-sm text-amber-800">
          {zh ? "建议配置缺少模型：" : "Suggestion unavailable: "}
          {missing.join(", ")}
        </p>
      )}
      <div className="max-h-96 space-y-3 overflow-y-auto">
        {status.roles.map((role) => {
          const selected = draft[role.id] ?? "";
          const effective = selected || status.selected_model;
          const model = status.models.find((item) => item.id === effective);
          return (
            <div
              key={role.id}
              className="grid items-center gap-2 border-b pb-3 sm:grid-cols-[1fr_2fr_auto]"
            >
              <label htmlFor={`copilot-role-${role.id}`} className="text-sm">
                {role.label}
                <span className="block font-mono text-xs text-gray-500">
                  {role.id}
                </span>
              </label>
              <div>
                <select
                  id={`copilot-role-${role.id}`}
                  data-testid={`copilot-role-${role.id}`}
                  className="w-full rounded border p-2 text-sm"
                  value={selected}
                  disabled={busy}
                  onChange={(event) => {
                    const value = event.target.value;
                    setDraft((old) => {
                      const next = { ...old };
                      if (value) next[role.id] = value;
                      else delete next[role.id];
                      return next;
                    });
                    setTested(null);
                  }}
                >
                  <option value="">
                    {zh ? "继承默认" : "Use default"} (
                    {status.selected_model ?? "—"})
                  </option>
                  {selected && !known.has(selected) && (
                    <option value={selected}>{selected} (unavailable)</option>
                  )}
                  {status.models.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name} · {item.vendor ?? ""} ({item.id})
                    </option>
                  ))}
                </select>
                <p className="mt-1 font-mono text-xs text-gray-500">
                  {effective ?? "—"} · {model?.api ?? "unavailable"}
                </p>
              </div>
              <button
                type="button"
                className="rounded border px-2 py-2 text-xs disabled:opacity-50"
                disabled={busy || dirty || !model}
                onClick={() => void run(role.id)}
                data-testid={`copilot-test-role-${role.id}`}
              >
                {zh ? "测试（消耗额度）" : "Test (uses allowance)"}
              </button>
            </div>
          );
        })}
      </div>
      <button
        type="button"
        className="mt-3 rounded bg-blue-700 px-3 py-2 text-sm text-white disabled:opacity-50"
        disabled={busy || !dirty}
        onClick={() => void run()}
        data-testid="copilot-save-routing"
      >
        {zh ? "保存角色配置" : "Save role routing"}
      </button>
      {dirty && (
        <span className="ml-3 text-sm text-amber-800">
          {zh
            ? "尚未保存；保存后才可测试角色"
            : "Unsaved; save before testing roles"}
        </span>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-700">
          {error}{" "}
          {zh ? "请刷新状态后重试。" : "Refresh status before retrying."}
        </p>
      )}
      {tested && (
        <p
          role="status"
          className="mt-2 text-sm text-green-800"
          data-testid="copilot-role-test-result"
        >
          {tested}
        </p>
      )}
    </details>
  );
}
