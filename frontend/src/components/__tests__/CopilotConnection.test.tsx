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
import {
  copilotAction,
  testCopilot,
  copilotStatusSchema,
  type CopilotStatus,
} from "../../services/copilot";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ i18n: { language: "en" } }),
}));
vi.mock("../../services/copilot", async (original) => {
  const module = await original<typeof import("../../services/copilot")>();
  return { ...module, copilotAction: vi.fn(), testCopilot: vi.fn() };
});
const status: CopilotStatus = {
  provider_enabled: true,
  github_authorized: false,
  authenticated: false,
  selected_model: null,
  models: [],
  login: null,
};

beforeEach(() => {
  vi.mocked(copilotAction).mockReset();
  vi.mocked(testCopilot).mockReset();
});
afterEach(cleanup);

describe("Native Copilot connection", () => {
  it("shows an explicit provider warning and never auto-tests inference", async () => {
    vi.mocked(copilotAction).mockResolvedValue({
      ...status,
      provider_enabled: false,
    });
    render(<CopilotConnection />);
    await waitFor(() =>
      expect(screen.getByTestId("copilot-inactive")).toBeTruthy(),
    );
    expect(testCopilot).not.toHaveBeenCalled();
    expect(copilotAction).toHaveBeenCalledTimes(1);
  });

  it("validates the status boundary and forbids an external authorization link", () => {
    expect(copilotStatusSchema.safeParse(status).success).toBe(true);
    expect(
      copilotStatusSchema.safeParse({ ...status, authenticated: "yes" })
        .success,
    ).toBe(false);
    expect(
      copilotStatusSchema.safeParse({
        ...status,
        login: {
          attempt_id: "id",
          state: "pending",
          user_code: "CODE",
          verification_uri: "https://evil.example",
          expires_at: 100,
          interval: 5,
        },
      }).success,
    ).toBe(false);
  });

  it("cannot select or test before authorization", async () => {
    vi.mocked(copilotAction).mockResolvedValue(status);
    render(<CopilotConnection />);
    await waitFor(() => expect(copilotAction).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId("copilot-model-select")).toBeNull();
    expect(screen.queryByTestId("copilot-test")).toBeNull();
  });

  it("logout aborts an in-flight test and ignores its late success", async () => {
    const ready: CopilotStatus = {
      ...status,
      authenticated: true,
      github_authorized: true,
      selected_model: "gpt-6-astra",
    };
    let finish: (model: string) => void = () => {
      throw new Error("Test was not started");
    };
    const pending = new Promise<string>((resolve) => {
      finish = resolve;
    });
    vi.mocked(copilotAction).mockImplementation(async (action) =>
      action === "logout" ? status : ready,
    );
    vi.mocked(testCopilot).mockReturnValue(pending);
    render(<CopilotConnection />);
    await waitFor(() =>
      expect(screen.getByTestId("copilot-test")).toBeTruthy(),
    );
    fireEvent.click(screen.getByTestId("copilot-test"));
    await waitFor(() => expect(testCopilot).toHaveBeenCalledOnce());
    const signal = vi.mocked(testCopilot).mock.calls[0][0];
    fireEvent.click(screen.getByTestId("copilot-logout"));
    await waitFor(() =>
      expect(screen.queryByTestId("copilot-test")).toBeNull(),
    );
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      finish("late-model");
      await pending;
    });
    expect(screen.queryByTestId("copilot-test-result")).toBeNull();
  });
});
