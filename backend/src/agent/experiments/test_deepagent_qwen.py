"""
Experiment: Does create_deep_agent() work with Qwen/DashScope?

Tests:
1. Can Qwen handle 10+ built-in tools + our custom tools?
2. Does it use our financial tools (not filesystem tools) for stock queries?
3. Does SKILL.md progressive disclosure work (read_file for skills)?
4. Does AnthropicPromptCachingMiddleware cause errors with non-Anthropic models?

Usage:
    docker compose exec backend python -m src.agent.experiments.test_deepagent_qwen
"""

import asyncio
import sys
import traceback
from pathlib import Path

import structlog

logger = structlog.get_logger()


async def run_experiment() -> dict[str, bool | str]:
    """Run the deepagents + Qwen compatibility experiment.

    Returns:
        dict with test results for each checkpoint.
    """
    results: dict[str, bool | str] = {}

    # ---------- Step 1: Import check ----------
    print("\n=== Step 1: Import deepagents ===")
    try:
        from deepagents import create_deep_agent
        from deepagents.backends import FilesystemBackend

        results["import_deepagents"] = True
        print("[PASS] deepagents imported successfully")
    except ImportError as e:
        results["import_deepagents"] = False
        results["import_error"] = str(e)
        print(f"[FAIL] Cannot import deepagents: {e}")
        return results

    # ---------- Step 2: Create LLM client ----------
    print("\n=== Step 2: Create Qwen LLM via ChatTongyi ===")
    try:
        from langchain_community.chat_models import ChatTongyi

        from src.core.config import get_settings

        settings = get_settings()
        llm = ChatTongyi(
            model_name=settings.default_llm_model,
            dashscope_api_key=settings.dashscope_api_key,
            model_kwargs={"result_format": "message"},
            request_timeout=60,
        )
        results["create_llm"] = True
        print(f"[PASS] ChatTongyi created with model={settings.default_llm_model}")
    except Exception as e:
        results["create_llm"] = False
        results["llm_error"] = str(e)
        print(f"[FAIL] Cannot create LLM: {e}")
        return results

    # ---------- Step 3: Create a real financial tool ----------
    print("\n=== Step 3: Create financial tool ===")
    try:
        from src.services.alphavantage_market_data import AlphaVantageMarketDataService
        from src.services.formatters import AlphaVantageResponseFormatter

        av_service = AlphaVantageMarketDataService(settings=settings)
        formatter = AlphaVantageResponseFormatter()

        from src.agent.tools.alpha_vantage.fundamentals import create_fundamental_tools

        tools = create_fundamental_tools(av_service, formatter)
        # get_company_overview is the first tool
        overview_tool = tools[0]
        results["create_tool"] = True
        print(
            f"[PASS] Financial tool created: "
            f"{getattr(overview_tool, 'name', 'unknown')}"
        )
    except Exception as e:
        results["create_tool"] = False
        results["tool_error"] = str(e)
        print(f"[FAIL] Cannot create tool: {e}")
        traceback.print_exc()
        return results

    # ---------- Step 4: Create deep agent with SKILL.md ----------
    print("\n=== Step 4: Create deep agent with skills + tools ===")
    skills_root = Path(__file__).resolve().parent.parent / "skills"
    skills_dir = str(skills_root / "technical")
    backend_root = str(skills_root.parent)

    print(f"  Skills dir: {skills_dir}")
    print(f"  Backend root: {backend_root}")
    print(f"  Skills exist: {Path(skills_dir).exists()}")
    skill_md = skills_root / "technical" / "trend-detection" / "SKILL.md"
    print(f"  SKILL.md exists: {skill_md.exists()}")

    try:
        agent = create_deep_agent(
            model=llm,
            tools=[overview_tool],
            skills=[skills_dir],
            backend=FilesystemBackend(root_dir=backend_root),
            system_prompt=(
                "You are a technical stock analyst. "
                "Use financial tools to analyze stocks. "
                "DO NOT use filesystem tools (ls, write_file, edit_file) "
                "for analysis - only use read_file to load SKILL.md workflows."
            ),
        )
        results["create_agent"] = True
        print("[PASS] Deep agent created successfully")

        # Inspect what tools the agent has
        if hasattr(agent, "tools"):
            tool_names = [getattr(t, "name", str(t)) for t in agent.tools]
            print(f"  Agent tools: {tool_names}")
            results["agent_tool_names"] = str(tool_names)
    except Exception as e:
        results["create_agent"] = False
        results["agent_error"] = str(e)
        print(f"[FAIL] Cannot create agent: {e}")
        traceback.print_exc()
        return results

    # ---------- Step 5: Invoke the agent with a stock query ----------
    print("\n=== Step 5: Invoke agent with stock analysis query ===")
    print("  Sending: 'Get the company overview for AAPL'")
    print("  (Using simple query to test tool calling ability)")

    try:
        result = await agent.ainvoke(
            {"messages": [("user", "Get the company overview for AAPL")]},
            config={"configurable": {"thread_id": "exp_001"}},
        )

        results["invoke_agent"] = True
        print("[PASS] Agent invocation completed")

        # Analyze messages
        messages = result.get("messages", [])
        print(f"  Total messages: {len(messages)}")

        tool_calls_made = []
        filesystem_tools_used = []
        financial_tools_used = []
        for msg in messages:
            cls_name = msg.__class__.__name__
            name = getattr(msg, "name", "")

            if cls_name == "ToolMessage":
                tool_name = name or getattr(msg, "tool_call_id", "")
                tool_calls_made.append(tool_name)
                if tool_name in ("ls", "write_file", "edit_file", "glob", "grep"):
                    filesystem_tools_used.append(tool_name)
                elif tool_name in ("get_company_overview", "read_file"):
                    financial_tools_used.append(tool_name)

            # Print last AI message as response
            if cls_name == "AIMessage" and msg.content:
                content_preview = str(msg.content)[:300]
                print(f"\n  [{cls_name}] {name}: {content_preview}...")

        print(f"\n  Tool calls: {tool_calls_made}")
        results["tool_calls"] = str(tool_calls_made)
        results["filesystem_tools_used"] = str(filesystem_tools_used)
        results["financial_tools_used"] = str(financial_tools_used)

        # Check: did it use get_company_overview?
        used_financial = any(
            "get_company_overview" in str(t) for t in tool_calls_made
        )
        results["used_financial_tool"] = used_financial
        if used_financial:
            print("[PASS] Agent used get_company_overview (our financial tool)")
        else:
            print("[WARN] Agent did NOT use get_company_overview")

        # Check: did it avoid filesystem tools for analysis?
        used_filesystem_for_analysis = any(
            t in ("ls", "write_file", "edit_file", "glob", "grep")
            for t in tool_calls_made
        )
        results["avoided_filesystem_abuse"] = not used_filesystem_for_analysis
        if not used_filesystem_for_analysis:
            print("[PASS] Agent did not misuse filesystem tools")
        else:
            print(f"[WARN] Agent used filesystem tools: {filesystem_tools_used}")

    except Exception as e:
        results["invoke_agent"] = False
        results["invoke_error"] = str(e)
        print(f"[FAIL] Agent invocation failed: {e}")
        traceback.print_exc()

    return results


def main():
    print("=" * 60)
    print("EXPERIMENT: deepagents + Qwen/DashScope Compatibility")
    print("=" * 60)

    results = asyncio.run(run_experiment())

    print("\n" + "=" * 60)
    print("EXPERIMENT RESULTS SUMMARY")
    print("=" * 60)
    for key, value in results.items():
        status = "PASS" if value is True else ("FAIL" if value is False else "INFO")
        print(f"  [{status}] {key}: {value}")

    # Overall verdict
    critical_checks = [
        "import_deepagents",
        "create_llm",
        "create_agent",
        "invoke_agent",
    ]
    all_critical_pass = all(results.get(k) is True for k in critical_checks)

    print("\n" + "-" * 40)
    if all_critical_pass:
        print("VERDICT: deepagents + Qwen COMPATIBLE")
        print("  Proceed to Phase B (full migration)")
    else:
        failed = [k for k in critical_checks if results.get(k) is not True]
        print(f"VERDICT: deepagents + Qwen INCOMPATIBLE")
        print(f"  Failed checks: {failed}")
        print("  Fallback: Use SKILL.md format with custom loader")

    return 0 if all_critical_pass else 1


if __name__ == "__main__":
    sys.exit(main())
