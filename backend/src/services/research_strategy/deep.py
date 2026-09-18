"""Deep's confirmed-strategy verdict is a research stance, not the legacy BUY/SELL schema."""

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from ...models.research_strategy import StrategyConclusion, StrategyConclusions
from ..evidence.context import current_snapshots, reminder
from .context import current
from .service import apply_conclusions


async def verdict(agent: Any, state: dict[str, Any], config: Any) -> dict[str, Any]:
    from ...agent.prompt_registry import get_prompt

    values = current()
    spec = get_prompt("strategy-conclusion")
    for review in values.values():
        review.prompt_versions[spec.prompt_id] = spec.versioned_id
    prompt = spec.render(
        reviews=json.dumps(
            [r.model_dump(mode="json") for r in values.values()], ensure_ascii=False
        ),
        research=str(state.get("research_report", "")),
    )
    prompt += reminder(str(state["symbol"]))
    result = StrategyConclusion.model_validate(
        await agent.verdict_llm.with_structured_output(StrategyConclusion).ainvoke(
            [HumanMessage(content=prompt)], config=config
        )
    )
    apply_conclusions(
        values, current_snapshots(), StrategyConclusions(conclusions=[result])
    )
    return {
        "messages": [
            AIMessage(content=result.report_markdown, name="Research committee")
        ],
        "research_report": result.report_markdown,
        "verdict": result.model_dump(mode="json"),
        "prompt_versions": {
            **state.get("prompt_versions", {}),
            spec.prompt_id: spec.versioned_id,
        },
    }
