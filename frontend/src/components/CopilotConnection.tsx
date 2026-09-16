import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import CopilotRoleRouting from "./CopilotRoleRouting";
import {
  copilotAction,
  copilotError,
  testCopilot,
  type CopilotAction,
  type CopilotStatus,
} from "../services/copilot";

export default function CopilotConnection() {
  const { i18n } = useTranslation();
  const zh = i18n.language.startsWith("zh");
  const [status, setStatus] = useState<CopilotStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [choice, setChoice] = useState("");
  const [tested, setTested] = useState<string | null>(null);
  const acceptRoutingStatus = useCallback((next: CopilotStatus) => {
    setStatus((current) =>
      current && (next.routing_revision ?? 0) < (current.routing_revision ?? 0)
        ? current
        : next,
    );
  }, []);
  const controller = useRef<AbortController | null>(null);
  const epoch = useRef(0);

  const act = useCallback(
    async (
      action: CopilotAction | "test",
      payload: Record<string, unknown> = {},
    ) => {
      controller.current?.abort();
      const active = new AbortController();
      controller.current = active;
      const current = ++epoch.current;
      setBusy(true);
      setError(null);
      setTested(null);
      try {
        if (action === "test") {
          const model = await testCopilot(active.signal, {
            model_id:
              typeof payload.model_id === "string"
                ? payload.model_id
                : undefined,
          });
          if (epoch.current === current) setTested(model);
        } else {
          const next = await copilotAction(action, payload, active.signal);
          if (epoch.current === current) {
            setStatus(next);
            setChoice(next.selected_model ?? "");
          }
        }
      } catch (err) {
        if (!active.signal.aborted && epoch.current === current)
          setError(copilotError(err));
      } finally {
        if (epoch.current === current) setBusy(false);
      }
    },
    [],
  );

  const cancelRequest = useCallback(() => {
    ++epoch.current;
    controller.current?.abort();
  }, []);

  useEffect(() => {
    void act("status");
    return cancelRequest;
  }, [act, cancelRequest]);

  useEffect(() => {
    const login = status?.login;
    if (busy || error || login?.state !== "pending") return;
    const timeout = window.setTimeout(
      () => {
        void act("poll", { attempt_id: login.attempt_id });
      },
      Math.max(1, login.interval) * 1000,
    );
    return () => window.clearTimeout(timeout);
  }, [act, busy, error, status]);

  const button =
    "rounded bg-blue-700 px-3 py-2 text-sm text-white disabled:opacity-50";
  return (
    <section
      className="space-y-4 rounded-lg bg-white p-5 shadow"
      data-testid="copilot-connection"
    >
      <div>
        <h2 className="text-lg font-semibold text-gray-900">
          GitHub Copilot · Native
        </h2>
        <p className="text-sm text-gray-600">
          {zh
            ? "直接连接 Copilot，无需 pi 或 bridge。需账号权益与可用额度；凭据仅保存在本应用后端。"
            : "Connect directly without pi or a bridge. Copilot entitlement and allowance are required. Credentials stay in this backend."}
        </p>
      </div>
      {status && !status.provider_enabled && (
        <p
          className="rounded bg-amber-50 p-3 text-sm text-amber-900"
          data-testid="copilot-inactive"
        >
          {zh
            ? "当前聊天尚未使用此 provider。设置 "
            : "This provider is not active for chat. Set "}
          <code>LLM_PROVIDER=github_copilot</code>
          {zh
            ? " 并 force-recreate backend；此处仍可单独授权和测试。"
            : " and force-recreate the backend. Authorization and an explicit test are still available here."}
        </p>
      )}
      <p className="text-sm text-gray-800" data-testid="copilot-status">
        {status?.authenticated
          ? zh
            ? "已授权（不代表已通过推理测试）"
            : "Authorized (inference not yet verified)"
          : status?.github_authorized
            ? zh
              ? "GitHub 已授权，需重试获取 Copilot 权限"
              : "GitHub authorized; retry Copilot access"
            : zh
              ? "尚未授权"
              : "Not authorized"}
      </p>
      {status?.login?.state === "pending" && (
        <div
          className="rounded border border-blue-200 bg-blue-50 p-4"
          data-testid="copilot-device"
        >
          <p>
            {zh
              ? "在 GitHub 页面输入设备码，然后确认授权："
              : "Enter this device code on GitHub and approve:"}
          </p>
          <p
            className="my-2 font-mono text-xl font-bold"
            data-testid="copilot-user-code"
          >
            {status.login.user_code}
          </p>
          <a
            href="https://github.com/login/device"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-800 underline"
          >
            {zh ? "打开 GitHub 授权页面" : "Open GitHub authorization"}
          </a>
          <p className="mt-2 text-sm">
            {zh
              ? "自动等待授权；密码和 2FA 只输入 GitHub 页面。"
              : "Waiting for approval. Enter passwords and 2FA only on GitHub."}
          </p>
        </div>
      )}
      {status?.login && status.login.state !== "pending" && (
        <p role="status" data-testid="copilot-login-ended">
          {zh ? "授权已结束：" : "Authorization ended: "}
          {status.login.state}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        {!status?.authenticated && status?.login?.state !== "pending" && (
          <button
            type="button"
            className={button}
            disabled={busy}
            onClick={() => void act("login")}
            data-testid="copilot-login"
          >
            {zh ? "登录 GitHub Copilot" : "Sign in to GitHub Copilot"}
          </button>
        )}
        {status?.github_authorized && (
          <button
            type="button"
            className={button}
            disabled={busy}
            onClick={() => void act("models")}
            data-testid="copilot-models"
          >
            {zh ? "刷新可用模型" : "Refresh available models"}
          </button>
        )}
        <button
          type="button"
          className={button}
          disabled={busy}
          onClick={() => void act("status")}
        >
          {zh ? "刷新状态" : "Refresh status"}
        </button>
        {(status?.github_authorized || status?.login) && (
          <button
            type="button"
            className="rounded border px-3 py-2 text-sm text-gray-800"
            onClick={() => void act("logout")}
            data-testid="copilot-logout"
          >
            {zh ? "取消 / 本地退出" : "Cancel / sign out locally"}
          </button>
        )}
      </div>
      {status?.authenticated && (
        <div className="space-y-3">
          <label
            className="block text-sm text-gray-700"
            htmlFor="copilot-model"
          >
            {zh
              ? "默认模型：未设置角色覆盖时使用。支持账号允许的 GPT、Gemini、Grok；排除 MAI。"
              : "Default model for roles without overrides. Permitted GPT, Gemini and Grok models are supported; MAI is excluded."}
          </label>
          <select
            id="copilot-model"
            data-testid="copilot-model-select"
            className="w-full rounded border p-2 text-gray-900"
            value={choice}
            disabled={busy}
            onChange={(event) => setChoice(event.target.value)}
          >
            <option value="">{zh ? "请选择模型" : "Select a model"}</option>
            {status.models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name} ({model.id})
              </option>
            ))}
          </select>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              className={button}
              disabled={busy || !choice}
              onClick={() =>
                void act("model", {
                  model_id: choice,
                  expected_revision: status.routing_revision,
                })
              }
              data-testid="copilot-save-model"
            >
              {zh ? "使用此模型" : "Use this model"}
            </button>
            <button
              type="button"
              className={button}
              disabled={busy || !status.selected_model}
              onClick={() =>
                void act("test", { model_id: status.selected_model })
              }
              data-testid="copilot-test"
            >
              {zh ? "测试连接（消耗额度）" : "Test connection (uses allowance)"}
            </button>
          </div>
          {status.models.length === 0 && (
            <p className="text-sm text-gray-600">
              {zh
                ? "请刷新模型。若仍为空，请检查 Copilot 权益或在官方客户端启用支持的模型。"
                : "Refresh models. If none appear, check entitlement or enable a supported model in an official client."}
            </p>
          )}
        </div>
      )}
      {status?.authenticated && (
        <CopilotRoleRouting
          key={status.routing_revision ?? 0}
          status={status}
          onStatus={acceptRoutingStatus}
        />
      )}
      {busy && (
        <p role="status" className="text-sm text-gray-500">
          {zh ? "处理中…" : "Working…"}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      {tested && (
        <p
          role="status"
          className="text-sm text-green-800"
          data-testid="copilot-test-result"
        >
          {zh
            ? "原生结构化推理测试通过："
            : "Native structured inference passed: "}
          {tested}
        </p>
      )}
    </section>
  );
}
