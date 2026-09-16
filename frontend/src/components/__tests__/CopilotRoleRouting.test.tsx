import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CopilotConnection from "../CopilotConnection";
import CopilotRoleRouting from "../CopilotRoleRouting";
import { copilotAction, type CopilotStatus } from "../../services/copilot";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ i18n: { language: "en" } }),
}));
vi.mock("../../services/copilot", async (original) => ({
  ...(await original<typeof import("../../services/copilot")>()),
  copilotAction: vi.fn(),
  testCopilot: vi.fn(),
}));
const ready: CopilotStatus = {
  provider_enabled: true,
  github_authorized: true,
  authenticated: true,
  selected_model: "gpt-6-astra",
  login: null,
  routing_revision: 1,
  role_models: {},
  roles: [{ id: "simple_chat", label: "Simple chat" }],
  recommended_role_models: { simple_chat: "gemini-3.8-flash" },
  models: [
    {
      id: "gpt-6-astra",
      name: "GPT",
      max_output_tokens: 4096,
      api: "openai-responses",
    },
    {
      id: "gemini-3.8-flash",
      name: "Gemini",
      max_output_tokens: 4096,
      api: "openai-completions",
    },
  ],
};
beforeEach(() => {
  vi.mocked(copilotAction).mockReset();
});
afterEach(cleanup);

describe("Role routing", () => {
  it("preset is a draft until saved with its expected revision", async () => {
    const onStatus = vi.fn();
    vi.mocked(copilotAction).mockResolvedValue({
      ...ready,
      routing_revision: 2,
    });
    render(<CopilotRoleRouting status={ready} onStatus={onStatus} />);
    fireEvent.click(screen.getByTestId("copilot-preset"));
    expect(copilotAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("copilot-save-routing"));
    await waitFor(() => expect(onStatus).toHaveBeenCalledOnce());
    expect(copilotAction).toHaveBeenCalledWith(
      "routing",
      {
        role_models: { simple_chat: "gemini-3.8-flash" },
        expected_revision: 1,
      },
      expect.any(AbortSignal),
    );
  });

  it("cannot apply an incomplete suggested preset", () => {
    render(
      <CopilotRoleRouting
        status={{
          ...ready,
          recommended_role_models: { sub_news: "missing-model" },
        }}
        onStatus={vi.fn()}
      />,
    );
    expect(
      (screen.getByTestId("copilot-preset") as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(screen.getByText(/missing-model/)).toBeTruthy();
  });

  it("late role-save cannot resurrect the UI after logout in the same render batch", async () => {
    let finishSave: (state: CopilotStatus) => void = () => undefined;
    let finishLogout: (state: CopilotStatus) => void = () => undefined;
    const save = new Promise<CopilotStatus>((resolve) => {
      finishSave = resolve;
    });
    const logout = new Promise<CopilotStatus>((resolve) => {
      finishLogout = resolve;
    });
    vi.mocked(copilotAction).mockImplementation(async (action) =>
      action === "routing" ? save : action === "logout" ? logout : ready,
    );
    render(<CopilotConnection />);
    await waitFor(() =>
      expect(screen.getByTestId("copilot-preset")).toBeTruthy(),
    );
    fireEvent.click(screen.getByTestId("copilot-preset"));
    fireEvent.click(screen.getByTestId("copilot-save-routing"));
    fireEvent.click(screen.getByTestId("copilot-logout"));
    await act(async () => {
      finishLogout({
        ...ready,
        authenticated: false,
        github_authorized: false,
        selected_model: null,
        role_models: {},
        routing_revision: 3,
      });
      finishSave({
        ...ready,
        role_models: { simple_chat: "gemini-3.8-flash" },
        routing_revision: 2,
      });
      await Promise.all([save, logout]);
    });
    expect(screen.queryByTestId("copilot-routing")).toBeNull();
    expect(screen.getByTestId("copilot-login")).toBeTruthy();
  });
});
