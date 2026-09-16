import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DecisionAssessments from "../DecisionAssessments";
import { listAssessments } from "../../../services/decisionAssessments";
vi.mock("../../../services/decisionAssessments", () => ({
  listAssessments: vi.fn(),
  getAssessment: vi.fn(),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ i18n: { language: "en" } }),
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
function mount() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <DecisionAssessments />
    </QueryClientProvider>,
  );
}
describe("assessment visibility", () => {
  it("shows explicit Stage A containment even without assessments", async () => {
    vi.mocked(listAssessments).mockResolvedValue([]);
    mount();
    expect(
      await screen.findByTestId("assessment-stage-a-notice"),
    ).toHaveTextContent("Non-actionable research only");
    expect(
      screen.queryByRole("button", { name: /approve|execute/i }),
    ).toBeNull();
  });
  it("does not invent an empty successful assessment on a failed fetch", async () => {
    vi.mocked(listAssessments).mockRejectedValue(new Error("offline"));
    mount();
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.queryByTestId("assessment-batch")).toBeNull();
  });
});
