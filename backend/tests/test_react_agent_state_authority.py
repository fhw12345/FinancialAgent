"""Tests that ReAct cross-turn state is supplied explicitly from MongoDB."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from src.agent.langgraph_react_agent import FinancialAnalysisReActAgent


@pytest.mark.asyncio
async def test_react_invocation_has_no_thread_id_or_checkpointer_state():
    agent = FinancialAnalysisReActAgent.__new__(FinancialAnalysisReActAgent)
    invocation = AsyncMock(
        return_value={"messages": [AIMessage(content="Acknowledged")]}
    )
    agent.agent = SimpleNamespace(ainvoke=invocation)
    agent.langfuse_enabled = False
    agent.langfuse_client = None

    result = await agent.ainvoke(
        user_message="What was the previous value?",
        conversation_history=[
            {"role": "user", "content": "Remember ORBIT-742"},
            {"role": "assistant", "content": "Acknowledged"},
        ],
        language="en",
        chat_id="chat_1",
    )

    config = invocation.await_args.kwargs["config"]
    invocation_messages = invocation.await_args.args[0]["messages"]
    assert "configurable" not in config
    assert not hasattr(agent, "checkpointer")
    assert invocation_messages[0].content == "Remember ORBIT-742"
    assert invocation_messages[1].content == "Acknowledged"
    assert invocation_messages[2].content.count("Respond in English") == 1
    assert result["final_answer"] == "Acknowledged"
