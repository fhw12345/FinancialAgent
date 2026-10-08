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
import { CreatePaperForm } from "../PaperForms";
import { createPaper } from "../../../../services/paperLedger";
vi.mock("../../../../services/paperLedger", () => ({
  createPaper: vi.fn(),
  journalPaper: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
function mount() {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <CreatePaperForm saved={vi.fn()} />
    </QueryClientProvider>,
  );
}
it("opening a paper form neither invents capital/costs nor calls the API", () => {
  mount();
  for (const id of [
    "paper-initial-cash",
    "paper-commission",
    "paper-slippage",
    "paper-symbols",
  ])
    expect(screen.getByTestId(id)).toHaveValue("");
  expect(screen.getByTestId("paper-create-ack")).not.toBeChecked();
  expect(screen.getByTestId("paper-create")).toBeDisabled();
  expect(createPaper).not.toHaveBeenCalled();
});
it("keeps monetary input as exact user strings and requires consent", async () => {
  mount();
  fireEvent.change(screen.getByTestId("paper-name"), {
    target: { value: "My scenario" },
  });
  fireEvent.change(screen.getByTestId("paper-initial-cash"), {
    target: { value: "10000.00" },
  });
  fireEvent.change(screen.getByTestId("paper-symbols"), {
    target: { value: "aapl, msft" },
  });
  fireEvent.change(screen.getByTestId("paper-commission"), {
    target: { value: "0" },
  });
  fireEvent.change(screen.getByTestId("paper-slippage"), {
    target: { value: "10.5" },
  });
  fireEvent.submit(screen.getByTestId("paper-create-form"));
  expect(createPaper).not.toHaveBeenCalled();
  vi.mocked(createPaper).mockRejectedValue(new Error("API rejected"));
  fireEvent.click(screen.getByTestId("paper-create-ack"));
  fireEvent.submit(screen.getByTestId("paper-create-form"));
  await waitFor(() => expect(createPaper).toHaveBeenCalledTimes(1));
  expect(vi.mocked(createPaper).mock.calls.at(0)?.[0]).toEqual({
    name: "My scenario",
    initial_cash: "10000.00",
    symbols: ["AAPL", "MSFT"],
    commission_bps: "0",
    slippage_bps: "10.5",
  });
  expect(await screen.findByRole("alert")).toBeVisible();
});
