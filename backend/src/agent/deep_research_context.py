"""Bounded structured context for multi-turn Deep Research."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .symbol_tokens import extract_explicit_symbols

_EN_HORIZON_RE = re.compile(
    r"\b(\d+)\s*[- ]?(day|week|month|year)s?\b",
    re.IGNORECASE,
)
_ZH_HORIZON_RE = re.compile(r"(\d+)\s*(天|周|个月|月|年)")

_RISK_MARKERS = {
    "conservative": ("conservative", "保守", "低风险"),
    "moderate": ("moderate", "balanced", "中等风险", "稳健"),
    "aggressive": ("aggressive", "high risk", "激进", "高风险"),
}
_CONSTRAINT_MARKERS = {
    "valuation_focus": ("valuation only", "focus on valuation", "只看估值", "估值为主"),
    "downside_focus": ("downside", "bear case", "下行", "悲观情景", "反方"),
    "technical_focus": (
        "technical only",
        "focus on technical",
        "只看技术",
        "技术面为主",
    ),
    "fundamental_focus": (
        "fundamentals only",
        "focus on fundamentals",
        "只看基本面",
        "基本面为主",
    ),
    "exclude_news": ("exclude news", "no news", "不要新闻", "排除新闻"),
    "adversarial_review": (
        "challeng",
        "adversarial",
        "counterargument",
        "质疑",
        "反驳",
        "反方",
    ),
}
_FOLLOW_UP_MARKERS = (
    "that thesis",
    "previous thesis",
    "same ",
    "continue",
    "follow up",
    "刚才",
    "上次",
    "之前",
    "继续",
    "同样",
    "沿用",
    "该结论",
    "这个结论",
)
_FOCUS_CONSTRAINTS = {
    "valuation_focus",
    "technical_focus",
    "fundamental_focus",
}
_HORIZON_REUSE_MARKERS = (
    "same horizon",
    "same time horizon",
    "previous horizon",
    "沿用之前的周期",
    "同样的周期",
    "相同周期",
    "之前的周期",
)
_RISK_REUSE_MARKERS = (
    "same risk",
    "same risk tolerance",
    "previous risk",
    "沿用之前的风险",
    "同样的风险",
    "相同风险",
    "之前的风险",
)
_CONSTRAINT_REUSE_MARKERS = (
    "same constraints",
    "same assumptions",
    "same requirements",
    "previous constraints",
    "沿用之前的约束",
    "同样的约束",
    "相同约束",
    "之前的约束",
)


@dataclass(frozen=True)
class ResearchTurn:
    """One bounded conversation turn used by Deep Research."""

    role: str
    content: str


@dataclass(frozen=True)
class DeepResearchContext:
    """Structured context shared across Deep Research graph nodes."""

    confirmed_symbol: str | None
    symbol_candidates: tuple[str, ...]
    current_request: str
    previous_user_request: str | None
    previous_assistant_report: str | None
    investment_horizon: str | None
    risk_tolerance: str | None
    constraints: tuple[str, ...]
    relevant_turns: tuple[ResearchTurn, ...]
    truncated: bool
    max_render_chars: int

    @classmethod
    def from_history(
        cls,
        *,
        current_request: str,
        conversation_history: list[dict[str, str]] | None,
        max_turns: int = 6,
        max_turn_chars: int = 1200,
        max_total_chars: int = 6000,
        max_current_request_chars: int = 2000,
    ) -> DeepResearchContext:
        """Build bounded context from Mongo-authoritative prior turns."""
        normalized_request = re.sub(r"\s+", " ", current_request).strip()
        request_truncated = len(normalized_request) > max_current_request_chars
        if request_truncated:
            if max_current_request_chars > 3:
                normalized_request = (
                    normalized_request[: max_current_request_chars - 3].rstrip() + "..."
                )
            else:
                normalized_request = normalized_request[:max_current_request_chars]

        source_turns = [
            turn
            for turn in (conversation_history or [])
            if turn.get("role") in ("user", "assistant")
            and (turn.get("content") or "").strip()
        ]
        selected = source_turns[-max_turns:]
        truncated = request_truncated or len(selected) < len(source_turns)
        bounded_reversed: list[ResearchTurn] = []
        total_chars = 0

        for source_turn in reversed(selected):
            content = re.sub(r"\s+", " ", source_turn["content"]).strip()
            if len(content) > max_turn_chars:
                content = content[: max_turn_chars - 3].rstrip() + "..."
                truncated = True
            remaining = max_total_chars - total_chars
            if remaining <= 0:
                truncated = True
                break
            if len(content) > remaining:
                if remaining > 3:
                    content = content[: remaining - 3].rstrip() + "..."
                else:
                    content = content[:remaining]
                truncated = True
            bounded_reversed.append(
                ResearchTurn(role=source_turn["role"], content=content)
            )
            total_chars += len(content)

        bounded = list(reversed(bounded_reversed))
        initial_symbol_candidates = cls._extract_symbol_candidates(bounded)
        if initial_symbol_candidates:
            bounded = cls._select_latest_symbol_segment(
                bounded,
                initial_symbol_candidates[0],
            )
        previous_user = next(
            (turn.content for turn in reversed(bounded) if turn.role == "user"),
            None,
        )
        previous_assistant = next(
            (turn.content for turn in reversed(bounded) if turn.role == "assistant"),
            None,
        )
        historical_user_text = "\n".join(
            turn.content for turn in bounded if turn.role == "user"
        )
        symbol_candidates = cls._extract_symbol_candidates(bounded)
        historical_constraints: tuple[str, ...] = ()
        for research_turn in bounded:
            if research_turn.role == "user":
                historical_constraints = cls._merge_constraints(
                    historical_constraints,
                    cls._extract_constraints(research_turn.content),
                )
        current_constraints = cls._extract_constraints(normalized_request)

        return cls(
            confirmed_symbol=symbol_candidates[0] if symbol_candidates else None,
            symbol_candidates=symbol_candidates,
            current_request=normalized_request,
            previous_user_request=previous_user,
            previous_assistant_report=previous_assistant,
            investment_horizon=(
                cls._extract_horizon(normalized_request)
                or cls._extract_horizon(historical_user_text)
            ),
            risk_tolerance=(
                cls._extract_risk_tolerance(normalized_request)
                or cls._extract_risk_tolerance(historical_user_text)
            ),
            constraints=cls._merge_constraints(
                historical_constraints,
                current_constraints,
            ),
            relevant_turns=tuple(bounded),
            truncated=truncated,
            max_render_chars=max_total_chars,
        )

    @property
    def allows_symbol_reuse(self) -> bool:
        """Return whether the current request is a deictic follow-up."""
        lowered = self.current_request.lower()
        return any(marker in lowered for marker in _FOLLOW_UP_MARKERS)

    def for_new_symbol(self) -> DeepResearchContext:
        """Drop target-specific history while honoring explicit carry-over."""
        current_only = self.from_history(
            current_request=self.current_request,
            conversation_history=[],
            max_total_chars=self.max_render_chars,
        )
        lowered = self.current_request.lower()
        reuse_constraints = any(
            marker in lowered for marker in _CONSTRAINT_REUSE_MARKERS
        )
        reuse_horizon = reuse_constraints or any(
            marker in lowered for marker in _HORIZON_REUSE_MARKERS
        )
        reuse_risk = reuse_constraints or any(
            marker in lowered for marker in _RISK_REUSE_MARKERS
        )

        return replace(
            current_only,
            investment_horizon=(
                current_only.investment_horizon
                or (self.investment_horizon if reuse_horizon else None)
            ),
            risk_tolerance=(
                current_only.risk_tolerance
                or (self.risk_tolerance if reuse_risk else None)
            ),
            constraints=(
                self._merge_constraints(self.constraints, current_only.constraints)
                if reuse_constraints
                else current_only.constraints
            ),
        )

    def render(
        self,
        *,
        symbol: str,
        previous_report_char_limit: int | None = None,
    ) -> str:
        """Render a prompt block with an optional prior-report excerpt limit."""
        lines = [
            "=== RESEARCH REQUEST CONTEXT ===",
            f"Confirmed symbol: {symbol}",
            f"Current request: {self.current_request}",
        ]
        if self.previous_user_request:
            lines.append(f"Previous request: {self.previous_user_request}")
        if self.investment_horizon:
            lines.append(f"Investment horizon: {self.investment_horizon}")
        if self.risk_tolerance:
            lines.append(f"Risk tolerance: {self.risk_tolerance}")
        if self.constraints:
            lines.append("Constraints:")
            lines.extend(f"- {constraint}" for constraint in self.constraints)
        if self.previous_assistant_report:
            previous_report = self.previous_assistant_report
            if (
                previous_report_char_limit is not None
                and len(previous_report) > previous_report_char_limit
            ):
                if previous_report_char_limit > 3:
                    previous_report = (
                        previous_report[: previous_report_char_limit - 3].rstrip()
                        + "..."
                    )
                else:
                    previous_report = previous_report[:previous_report_char_limit]
            lines.extend(
                [
                    "Previous report excerpt:",
                    previous_report,
                ]
            )
        if self.truncated:
            lines.append("Context note: prior conversation was truncated to limits.")
        closing = "\n=== END RESEARCH REQUEST CONTEXT ==="
        body = "\n".join(lines)
        if len(body) + len(closing) <= self.max_render_chars:
            return body + closing

        truncation_note = "\nContext note: rendered context truncated to limit."
        suffix = truncation_note + closing
        if self.max_render_chars <= len(suffix):
            return suffix[: self.max_render_chars]
        available = max(0, self.max_render_chars - len(suffix))
        return body[:available].rstrip() + suffix

    def metadata(self, *, symbol: str) -> dict[str, object]:
        """Return compact persistence/observability metadata."""
        return {
            "confirmed_symbol": symbol,
            "investment_horizon": self.investment_horizon,
            "risk_tolerance": self.risk_tolerance,
            "constraints": list(self.constraints),
            "relevant_turn_count": len(self.relevant_turns),
            "has_previous_report": self.previous_assistant_report is not None,
            "truncated": self.truncated,
        }

    @staticmethod
    def _extract_symbol_candidates(
        turns: list[ResearchTurn],
    ) -> tuple[str, ...]:
        candidates: list[str] = []
        for turn in reversed(turns):
            symbols = extract_explicit_symbols(turn.content)
            ordered_symbols = reversed(symbols) if turn.role == "user" else symbols
            for symbol in ordered_symbols:
                if symbol not in candidates:
                    candidates.append(symbol)
                if len(candidates) >= 3:
                    return tuple(candidates)
        return tuple(candidates)

    @staticmethod
    def _select_latest_symbol_segment(
        turns: list[ResearchTurn],
        target_symbol: str,
    ) -> list[ResearchTurn]:
        last_conflicting_index = -1
        target_indices: list[int] = []

        for index, turn in enumerate(turns):
            symbols = extract_explicit_symbols(turn.content)
            if target_symbol in symbols:
                target_indices.append(index)
            elif symbols:
                last_conflicting_index = index

        eligible_targets = [
            index for index in target_indices if index > last_conflicting_index
        ]
        if not eligible_targets:
            return turns

        boundary = eligible_targets[0]
        if (
            turns[boundary].role == "assistant"
            and boundary > last_conflicting_index + 1
            and turns[boundary - 1].role == "user"
        ):
            boundary -= 1
        return turns[boundary:]

    @staticmethod
    def _extract_horizon(text: str) -> str | None:
        matches: list[tuple[int, str]] = []
        for match in _EN_HORIZON_RE.finditer(text):
            value, unit = match.groups()
            matches.append(
                (
                    match.start(),
                    f"{value} {unit}{'' if value == '1' else 's'}",
                )
            )
        for match in _ZH_HORIZON_RE.finditer(text):
            value, unit = match.groups()
            matches.append((match.start(), f"{value}{unit}"))
        if not matches:
            return None
        return max(matches, key=lambda item: item[0])[1]

    @staticmethod
    def _extract_risk_tolerance(text: str) -> str | None:
        lowered = text.lower()
        matched = None
        matched_position = -1
        for risk, markers in _RISK_MARKERS.items():
            for marker in markers:
                marker_lower = marker.lower()
                if marker_lower.isascii():
                    matches = list(
                        re.finditer(
                            rf"\b{re.escape(marker_lower)}\b",
                            lowered,
                        )
                    )
                    position = matches[-1].start() if matches else -1
                else:
                    position = lowered.rfind(marker_lower)
                if position > matched_position:
                    matched = risk
                    matched_position = position
        return matched

    @staticmethod
    def _extract_constraints(text: str) -> tuple[str, ...]:
        lowered = text.lower()
        return tuple(
            constraint
            for constraint, markers in _CONSTRAINT_MARKERS.items()
            if any(marker.lower() in lowered for marker in markers)
        )

    @staticmethod
    def _merge_constraints(
        historical: tuple[str, ...],
        current: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(constraint in _FOCUS_CONSTRAINTS for constraint in current):
            historical = tuple(
                constraint
                for constraint in historical
                if constraint not in _FOCUS_CONSTRAINTS
            )
        return tuple(dict.fromkeys((*historical, *current)))
