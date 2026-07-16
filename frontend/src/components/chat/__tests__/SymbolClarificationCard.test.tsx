import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ClarificationRequiredEvent } from "../../../types/api";
import { SymbolClarificationCard } from "../SymbolClarificationCard";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const clarification: ClarificationRequiredEvent = {
  type: "clarification_required",
  clarification_type: "symbol",
  reason_code: "ambiguous_symbol",
  message: "Please select a company.",
  original_request: "Deeply analyze Alpha",
  candidates: [
    {
      symbol: "AAA",
      name: "Alpha A",
      exchange: "NYSE",
      confidence: 0.9,
    },
    {
      symbol: "AAB",
      name: "Alpha B",
      exchange: "NASDAQ",
      confidence: 0.85,
    },
  ],
};

describe("SymbolClarificationCard", () => {
  it("renders validated candidates", () => {
    render(<SymbolClarificationCard clarification={clarification} />);

    expect(screen.getByTestId("symbol-clarification")).toBeTruthy();
    expect(screen.getByText("AAA")).toBeTruthy();
    expect(screen.getByText("Alpha A · NYSE")).toBeTruthy();
    expect(screen.getByText("AAB")).toBeTruthy();
  });

  it("selects a candidate without submitting by itself", () => {
    const onSelect = vi.fn();
    render(
      <SymbolClarificationCard
        clarification={clarification}
        onSelectCandidate={onSelect}
      />,
    );

    fireEvent.click(screen.getByTestId("symbol-candidate-AAA"));

    expect(onSelect).toHaveBeenCalledOnce();
    expect(onSelect).toHaveBeenCalledWith(clarification.candidates[0]);
  });

  it("renders search guidance when no candidates exist", () => {
    render(
      <SymbolClarificationCard
        clarification={{ ...clarification, candidates: [] }}
      />,
    );

    expect(screen.getByText("chat:clarification.searchGuidance")).toBeTruthy();
  });
});
