import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { ReviewPolicyPanel } from "../ReviewPolicyPanel";
import {
  confirmReviewPolicy,
  type ReviewSettings,
} from "../../../services/decisionReviews";
vi.mock("../../../services/decisionReviews", async () => ({
  ...(await vi.importActual<typeof import("../../../services/decisionReviews")>(
    "../../../services/decisionReviews",
  )),
  confirmReviewPolicy: vi.fn(),
  deactivateReviewPolicy: vi.fn(),
  reconcileReviewAccount: vi.fn(),
}));
const state: ReviewSettings = {
  revision: 7,
  generation: 1,
  policy: null,
  versions: [],
  account_revision: "account",
  risk_policy_revision: 1,
  strategy_version: "strategy_" + "a".repeat(64),
  uncertain: false,
  in_flight: 0,
  current_batch_id: null,
  reasons: ["REVIEW_POLICY_UNCONFIRMED"],
  approval_available: true,
  execution_available: false,
};
function mount(value = state) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ReviewPolicyPanel state={value} changed={vi.fn()} />
    </QueryClientProvider>,
  );
}
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
it("opening the policy panel leaves limits, expiry and consent blank and makes no mutation", () => {
  mount();
  fireEvent.click(screen.getByTestId("configure-review-policy"));
  expect(screen.getByTestId("review-policy-sigma")).toHaveValue(null);
  expect(screen.getByTestId("review-policy-lifetime")).toHaveValue(null);
  expect(screen.getByTestId("review-policy-symbols")).toHaveValue("");
  expect(screen.getByTestId("review-policy-ack")).not.toBeChecked();
  expect(screen.getByTestId("confirm-review-policy")).toBeDisabled();
  expect(confirmReviewPolicy).not.toHaveBeenCalled();
});
it("requires the user's exact numeric inputs and every acknowledgment, binding visible revisions", async () => {
  vi.mocked(confirmReviewPolicy).mockResolvedValue(state);
  mount();
  fireEvent.click(screen.getByTestId("configure-review-policy"));
  fireEvent.change(screen.getByTestId("review-policy-symbols"), {
    target: { value: "aapl, msft" },
  });
  fireEvent.change(screen.getByTestId("review-policy-sigma"), {
    target: { value: ".25" },
  });
  fireEvent.change(screen.getByTestId("review-policy-lifetime"), {
    target: { value: "45" },
  });
  fireEvent.click(screen.getByTestId("review-policy-ack"));
  fireEvent.submit(screen.getByTestId("review-policy-form"));
  expect(confirmReviewPolicy).not.toHaveBeenCalled();
  fireEvent.click(screen.getByTestId("review-instrument-ack"));
  fireEvent.click(screen.getByTestId("review-evidence-ack"));
  fireEvent.submit(screen.getByTestId("review-policy-form"));
  // No default for model decisions: the explicit choice is still missing.
  expect(confirmReviewPolicy).not.toHaveBeenCalled();
  fireEvent.click(screen.getByTestId("review-model-disabled"));
  fireEvent.submit(screen.getByTestId("review-policy-form"));
  await waitFor(() => expect(confirmReviewPolicy).toHaveBeenCalledTimes(1));
  const sent = vi.mocked(confirmReviewPolicy).mock.calls.at(0);
  expect(sent?.[0]).toEqual({
    risk_policy_revision: 1,
    strategy_version: state.strategy_version,
    allowed_symbols: ["AAPL", "MSFT"],
    max_account_sigma: 0.25,
    lifetime_minutes: 45,
    acknowledged_contract: "manual-target-paper-review@1",
    instrument_attestation: "USD-US-nonfinancial-common-equities",
    evidence_acknowledgment: "forward-close-not-truth-or-historical-PIT",
    model_decisions: "disabled",
  });
  expect(sent?.[1]).toMatchObject({
    expected_revision: 7,
    expected_generation: 1,
  });
  expect(sent?.[1].request_id).toMatch(/^[A-Za-z0-9_-]{8,80}$/);
});
it("model decisions need explicit open/exit answers and acknowledgment", async () => {
  vi.mocked(confirmReviewPolicy).mockResolvedValue(state);
  mount();
  fireEvent.click(screen.getByTestId("configure-review-policy"));
  fireEvent.change(screen.getByTestId("review-policy-symbols"), {
    target: { value: "AAPL" },
  });
  fireEvent.change(screen.getByTestId("review-policy-sigma"), {
    target: { value: ".3" },
  });
  fireEvent.change(screen.getByTestId("review-policy-lifetime"), {
    target: { value: "30" },
  });
  for (const id of [
    "review-policy-ack",
    "review-instrument-ack",
    "review-evidence-ack",
    "review-model-enabled",
  ])
    fireEvent.click(screen.getByTestId(id));
  expect(screen.getByTestId("review-model-open-yes")).not.toBeChecked();
  expect(screen.getByTestId("review-model-open-no")).not.toBeChecked();
  fireEvent.submit(screen.getByTestId("review-policy-form"));
  expect(confirmReviewPolicy).not.toHaveBeenCalled();
  fireEvent.click(screen.getByTestId("review-model-open-no"));
  fireEvent.click(screen.getByTestId("review-model-exit-yes"));
  fireEvent.click(screen.getByTestId("review-model-ack"));
  fireEvent.submit(screen.getByTestId("review-policy-form"));
  await waitFor(() => expect(confirmReviewPolicy).toHaveBeenCalledTimes(1));
  expect(vi.mocked(confirmReviewPolicy).mock.calls.at(0)?.[0]).toMatchObject({
    model_decisions: "propose_for_human_review",
    model_may_open: false,
    model_may_exit: true,
    model_acknowledgment:
      "model-proposes-code-validates-human-decides-no-trade",
  });
});
it("cannot silently create a strategy or costs and cannot force-unlock an in-flight writer", () => {
  mount({
    ...state,
    strategy_version: null,
    risk_policy_revision: 0,
    uncertain: true,
    in_flight: 1,
  });
  fireEvent.click(screen.getByTestId("configure-review-policy"));
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Confirm risk costs and an active research strategy first",
  );
  expect(screen.queryByTestId("review-policy-form")).toBeNull();
  fireEvent.click(
    screen.getByLabelText("I inspected the declared account / 我已核对账户"),
  );
  expect(
    screen.getByRole("button", { name: "Record reconciliation / 登记核对" }),
  ).toBeDisabled();
  expect(confirmReviewPolicy).not.toHaveBeenCalled();
});
