import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AddTransactionModal } from "../AddTransactionModal";
vi.mock("../../SymbolSearch", () => ({
  SymbolSearch: ({
    onSymbolSelect,
  }: {
    onSymbolSelect: (symbol: string) => void;
  }) => (
    <button type="button" onClick={() => onSymbolSelect("AAPL")}>
      Choose AAPL
    </button>
  ),
}));
afterEach(cleanup);
it("manual quantity/price changes actually auto-calculate a submittable amount", async () => {
  const submit = vi.fn();
  render(<AddTransactionModal open onClose={vi.fn()} onSubmit={submit} />);
  fireEvent.click(screen.getByRole("button", { name: "Choose AAPL" }));
  fireEvent.change(screen.getByLabelText("Quantity"), {
    target: { value: "2" },
  });
  fireEvent.change(screen.getByLabelText("Execution Price ($)"), {
    target: { value: "100" },
  });
  expect(screen.getByLabelText("Total Amount ($)")).toHaveValue(200);
  fireEvent.click(
    screen.getByRole("button", { name: "Add Transaction" }),
  );
  await waitFor(() =>
    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        symbol: "AAPL",
        quantity: 2,
        price: 100,
        total_amount: 200,
      }),
    ),
  );
});
