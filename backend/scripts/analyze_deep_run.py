#!/usr/bin/env python3
"""
Case study script: Analyze the latest successful deep analysis run.

Examines tool execution times, sub-agent performance, debate quality,
and identifies improvement areas.

Usage (inside backend container):
    python scripts/analyze_deep_run.py
"""

import asyncio
import json
from datetime import datetime, timezone
from collections import defaultdict

from motor.motor_asyncio import AsyncIOMotorClient


MONGO_URL = "mongodb://mongodb:27017/financial_agent"
COLLECTION = "messages"


async def get_latest_deep_analysis(db):
    """Find the most recent successful deep analysis message."""
    collection = db[COLLECTION]

    # Query by presence of deep_events in raw_data (actual schema)
    cursor = collection.find(
        {"metadata.raw_data.deep_events": {"$exists": True}},
        sort=[("timestamp", -1)],
        limit=5,
    )
    results = []
    async for doc in cursor:
        meta = doc.get("metadata", {}) or {}
        raw_data = meta.get("raw_data", {}) or {}
        events = raw_data.get("deep_events", [])
        results.append(
            {
                "message_id": str(doc.get("_id", "")),
                "chat_id": doc.get("chat_id", ""),
                "content_preview": (doc.get("content", ""))[:200],
                "timestamp": doc.get("timestamp"),
                "event_count": len(events),
                "has_verdict": any(e.get("type") == "deep_verdict" for e in events),
                "input_tokens": meta.get("input_tokens", 0),
                "output_tokens": meta.get("output_tokens", 0),
                "events": events,
                "metadata": meta,
            }
        )
    return results


def analyze_tool_performance(events: list[dict]) -> dict:
    """Analyze tool execution times and success rates."""
    tool_starts = {}
    tool_results = []

    for e in events:
        if e.get("type") == "deep_tool_start":
            key = (e.get("subagent_name"), e.get("tool_name"), e.get("seq"))
            tool_starts[key] = e
        elif e.get("type") == "deep_tool_end":
            tool_results.append(
                {
                    "subagent": e.get("subagent_name"),
                    "tool": e.get("tool_name"),
                    "display_name": e.get("display_name", e.get("tool_name")),
                    "status": e.get("status"),
                    "duration_ms": e.get("duration_ms", 0),
                    "output_preview": e.get("output_preview", "")[:500],
                    "inputs": {},
                }
            )
            # Match inputs from start events
            for key, start_event in tool_starts.items():
                if key[0] == e.get("subagent_name") and key[1] == e.get("tool_name"):
                    tool_results[-1]["inputs"] = start_event.get("inputs", {})
                    break

    return {
        "total_tool_calls": len(tool_results),
        "successful": sum(1 for t in tool_results if t["status"] == "success"),
        "failed": sum(1 for t in tool_results if t["status"] != "success"),
        "tools": tool_results,
    }


def analyze_subagent_performance(events: list[dict]) -> dict:
    """Analyze sub-agent execution times and output quality."""
    subagent_results = []

    for e in events:
        if e.get("type") == "deep_subagent_result":
            result_summary = e.get("result_summary", "")
            subagent_results.append(
                {
                    "name": e.get("subagent_name"),
                    "display_name": e.get("display_name", e.get("subagent_name")),
                    "status": e.get("status"),
                    "duration_ms": e.get("duration_ms", 0),
                    "tool_count": e.get("tool_count", 0),
                    "result_length": len(result_summary),
                    "result_preview": result_summary[:800],
                }
            )

    return {
        "total_subagents": len(subagent_results),
        "subagents": subagent_results,
    }


def analyze_debate_quality(events: list[dict]) -> dict:
    """Analyze debate rounds, rebuttal, and verdict."""
    debate_rounds = []
    rebuttals = []
    verdict = None

    for e in events:
        if e.get("type") == "deep_debate_round":
            debate_rounds.append(
                {
                    "round": e.get("round", 0),
                    "concerns_text": e.get("debate_text", "")[:800],
                    "has_termination": e.get("has_termination_signal", False),
                }
            )
        elif e.get("type") == "deep_rebuttal_result":
            rebuttals.append(
                {
                    "rebuttal_text": e.get("rebuttal_text", "")[:800],
                    "duration_ms": e.get("duration_ms", 0),
                    "tool_count": e.get("tool_count", 0),
                }
            )
        elif e.get("type") == "deep_verdict":
            verdict = {
                "verdict_text": e.get("verdict_text", "")[:2000],
                "risk_level": e.get("risk_level"),
                "tool_count": e.get("tool_count", 0),
                "total_duration_ms": e.get("total_duration_ms", 0),
            }

    return {
        "debate_rounds": len(debate_rounds),
        "rounds": debate_rounds,
        "rebuttals": rebuttals,
        "verdict": verdict,
    }


def analyze_timeline(events: list[dict]) -> dict:
    """Reconstruct the full timeline with phases and gaps."""
    if not events:
        return {"phases": [], "total_duration_ms": 0}

    phases = []
    first_ts = None
    last_ts = None

    for e in events:
        ts_str = e.get("timestamp")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if first_ts is None:
                    first_ts = ts
                last_ts = ts
            except (ValueError, AttributeError):
                pass

        etype = e.get("type", "")
        if etype in (
            "deep_start",
            "deep_subagent_start",
            "deep_debate_start",
            "deep_rebuttal_start",
            "deep_synthesis_start",
            "deep_verdict",
        ):
            phases.append(
                {
                    "type": etype,
                    "timestamp": ts_str,
                    "seq": e.get("seq"),
                    "detail": e.get("subagent_name", e.get("symbol", "")),
                }
            )

    total_ms = 0
    if first_ts and last_ts:
        total_ms = int((last_ts - first_ts).total_seconds() * 1000)

    return {
        "phases": phases,
        "total_duration_ms": total_ms,
        "first_event": events[0].get("timestamp") if events else None,
        "last_event": events[-1].get("timestamp") if events else None,
    }


def analyze_tool_output_quality(tool_results: list[dict]) -> list[dict]:
    """Flag potential quality issues in tool outputs."""
    issues = []

    for t in tool_results:
        output = t.get("output_preview", "")
        tool_name = t.get("tool")

        # Check for empty or near-empty outputs
        if len(output) < 20:
            issues.append(
                {
                    "tool": tool_name,
                    "subagent": t.get("subagent"),
                    "issue": "VERY_SHORT_OUTPUT",
                    "detail": f"Output only {len(output)} chars: '{output}'",
                    "severity": "HIGH",
                }
            )

        # Check for error patterns in output
        error_patterns = [
            "error",
            "failed",
            "not found",
            "no data",
            "unavailable",
            "exception",
        ]
        output_lower = output.lower()
        for pattern in error_patterns:
            if pattern in output_lower:
                issues.append(
                    {
                        "tool": tool_name,
                        "subagent": t.get("subagent"),
                        "issue": "POSSIBLE_ERROR_IN_OUTPUT",
                        "detail": f"Contains '{pattern}': {output[:300]}",
                        "severity": "MEDIUM",
                    }
                )
                break

        # Check for suspiciously fast execution
        if t.get("duration_ms", 0) < 50 and t.get("status") == "success":
            issues.append(
                {
                    "tool": tool_name,
                    "subagent": t.get("subagent"),
                    "issue": "SUSPICIOUSLY_FAST",
                    "detail": f"Completed in {t['duration_ms']}ms — possibly cached or empty",
                    "severity": "LOW",
                }
            )

        # Check for very slow execution
        if t.get("duration_ms", 0) > 10000:
            issues.append(
                {
                    "tool": tool_name,
                    "subagent": t.get("subagent"),
                    "issue": "VERY_SLOW",
                    "detail": f"Took {t['duration_ms']}ms ({t['duration_ms']/1000:.1f}s)",
                    "severity": "MEDIUM",
                }
            )

    return issues


def print_section(title: str, content: str = ""):
    """Print a formatted section header."""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")
    if content:
        print(content)


def format_duration(ms) -> str:
    """Format milliseconds into human-readable duration."""
    if ms is None:
        return "N/A"
    ms = int(ms)
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        return f"{ms/1000:.1f}s"
    else:
        return f"{ms/60000:.1f}min"


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client.get_default_database()

    print_section("DEEP ANALYSIS CASE STUDY")
    print(f"  Timestamp: {datetime.now(timezone.utc).isoformat()}")

    # Get latest deep analyses
    analyses = await get_latest_deep_analysis(db)

    if not analyses:
        print("\n  No deep analysis messages found in database!")
        # Fallback: look for messages with raw_data at all
        print("\n  Checking for any messages with raw_data...")
        cursor = db[COLLECTION].find(
            {"metadata.raw_data": {"$exists": True}},
            sort=[("timestamp", -1)],
            limit=3,
        )
        async for doc in cursor:
            meta = doc.get("metadata", {}) or {}
            raw = meta.get("raw_data", {}) or {}
            print(
                f"    Found: raw_data keys={list(raw.keys())[:10]}, content={str(doc.get('content',''))[:100]}"
            )
        client.close()
        return

    print(f"\n  Found {len(analyses)} deep analysis message(s):")
    for i, a in enumerate(analyses):
        status = "COMPLETE" if a["has_verdict"] else "PARTIAL"
        print(
            f"    [{i}] {status} | {a['event_count']} events | "
            f"tokens: {a['input_tokens']}in/{a['output_tokens']}out | "
            f"{a['timestamp']}"
        )
        print(f"        Content: {a['content_preview'][:100]}...")

    # Pick the latest with a verdict (complete analysis)
    target = None
    for a in analyses:
        if a["has_verdict"]:
            target = a
            break

    if target is None:
        print("\n  No complete analysis (with verdict) found. Using latest partial.")
        target = analyses[0]

    events = target["events"]
    print(f"\n  Selected analysis: {target['timestamp']}")
    print(f"  Chat ID: {target['chat_id']}")
    print(f"  Events: {target['event_count']}")

    # ---- 1. TIMELINE ANALYSIS ----
    timeline = analyze_timeline(events)
    print_section("1. TIMELINE ANALYSIS")
    print(f"  Total duration: {format_duration(timeline['total_duration_ms'])}")
    print(f"  First event: {timeline['first_event']}")
    print(f"  Last event:  {timeline['last_event']}")
    print(f"\n  Phase transitions:")
    for p in timeline["phases"]:
        print(f"    seq={p['seq']:>3} | {p['type']:<25s} | {p['detail']}")

    # ---- 2. SUB-AGENT PERFORMANCE ----
    subagent_perf = analyze_subagent_performance(events)
    print_section("2. SUB-AGENT PERFORMANCE")
    print(f"  Total sub-agents invoked: {subagent_perf['total_subagents']}")

    for sa in subagent_perf["subagents"]:
        print(f"\n  --- {sa['display_name']} ({sa['name']}) ---")
        print(
            f"  Status: {sa['status']} | Duration: {format_duration(sa['duration_ms'])} | Tools used: {sa['tool_count']}"
        )
        print(f"  Output length: {sa['result_length']} chars")
        print(f"  Preview:")
        for line in sa["result_preview"].split("\n")[:15]:
            print(f"    {line}")

    # ---- 3. TOOL PERFORMANCE ----
    tool_perf = analyze_tool_performance(events)
    print_section("3. TOOL PERFORMANCE")
    print(f"  Total tool calls: {tool_perf['total_tool_calls']}")
    print(f"  Successful: {tool_perf['successful']} | Failed: {tool_perf['failed']}")

    # Group by tool name
    by_tool = defaultdict(list)
    for t in tool_perf["tools"]:
        by_tool[t["tool"]].append(t)

    print(f"\n  Per-tool breakdown:")
    for tool_name, calls in sorted(
        by_tool.items(), key=lambda x: -max(c["duration_ms"] for c in x[1])
    ):
        print(f"\n  {tool_name} ({len(calls)} call(s))")
        for c in calls:
            status_icon = "OK" if c["status"] == "success" else "FAIL"
            inputs_str = json.dumps(c.get("inputs", {}), default=str)[:120]
            print(
                f"    [{status_icon}] {format_duration(c['duration_ms']):>8s} | {c['subagent']:<20s} | inputs: {inputs_str}"
            )
            if c["output_preview"]:
                preview = c["output_preview"][:200].replace("\n", " ")
                print(f"      output: {preview}")

    # ---- 4. TOOL OUTPUT QUALITY ISSUES ----
    quality_issues = analyze_tool_output_quality(tool_perf["tools"])
    print_section("4. TOOL OUTPUT QUALITY ISSUES")
    if quality_issues:
        for issue in quality_issues:
            sev = issue["severity"]
            print(f"\n  [{sev}] {issue['issue']}")
            print(f"    Tool: {issue['tool']} (subagent: {issue['subagent']})")
            print(f"    Detail: {issue['detail'][:300]}")
    else:
        print("  No quality issues detected.")

    # ---- 5. DEBATE QUALITY ----
    debate = analyze_debate_quality(events)
    print_section("5. DEBATE QUALITY")
    print(f"  Debate rounds: {debate['debate_rounds']}")
    print(f"  Rebuttals: {len(debate['rebuttals'])}")

    for r in debate["rounds"]:
        print(f"\n  --- Round {r['round']} ---")
        print(f"  Termination signal: {r['has_termination']}")
        print(f"  Concerns:")
        for line in r["concerns_text"].split("\n")[:12]:
            print(f"    {line}")

    for i, reb in enumerate(debate["rebuttals"]):
        print(f"\n  --- Rebuttal {i+1} ---")
        print(
            f"  Duration: {format_duration(reb['duration_ms'])} | Tools used: {reb['tool_count']}"
        )
        print(f"  Text:")
        for line in reb["rebuttal_text"].split("\n")[:12]:
            print(f"    {line}")

    if debate["verdict"]:
        v = debate["verdict"]
        print(f"\n  --- VERDICT ---")
        print(f"  Risk level: {v['risk_level']}")
        print(
            f"  Total tools: {v['tool_count']} | Duration: {format_duration(v['total_duration_ms'])}"
        )
        print(f"  Verdict text:")
        for line in v["verdict_text"].split("\n")[:20]:
            print(f"    {line}")

    # ---- 6. TOKEN USAGE ----
    print_section("6. TOKEN USAGE")
    print(f"  Input tokens:  {target['input_tokens']:,}")
    print(f"  Output tokens: {target['output_tokens']:,}")
    total_tokens = (target["input_tokens"] or 0) + (target["output_tokens"] or 0)
    print(f"  Total tokens:  {total_tokens:,}")

    # ---- 7. COST METRICS ----
    print_section("7. COST METRICS")
    total_duration = timeline["total_duration_ms"]
    tool_count = tool_perf["total_tool_calls"]
    print(f"  Duration: {format_duration(total_duration)}")
    print(f"  Tool calls: {tool_count}")
    print(f"  Tokens: {total_tokens:,}")
    if total_duration > 0:
        print(f"  Tokens per second: {total_tokens / max(total_duration/1000, 1):.0f}")
    if tool_perf["tools"]:
        avg_tool = sum(t["duration_ms"] for t in tool_perf["tools"]) / len(
            tool_perf["tools"]
        )
        print(f"  Avg tool duration: {format_duration(avg_tool)}")

    # ---- 8. RAW EVENTS DUMP ----
    print_section("8. RAW EVENTS (compact)")
    for e in events:
        compact = {
            k: v
            for k, v in e.items()
            if k
            not in (
                "result_summary",
                "verdict_text",
                "debate_text",
                "rebuttal_text",
                "output_preview",
            )
        }
        for k, v in compact.items():
            if isinstance(v, str) and len(v) > 150:
                compact[k] = v[:150] + "..."
        print(
            f"  seq={e.get('seq', '?'):>3} | {e.get('type', 'unknown'):<25s} | "
            f"{json.dumps(compact, default=str)}"
        )

    # ---- 9. FULL CONTENT ----
    print_section("9. FULL ANALYSIS CONTENT (message)")
    print(target["content_preview"])
    # Print the rest
    # Re-read from metadata if available
    full_content = ""
    cursor = db[COLLECTION].find(
        {"metadata.raw_data.deep_events": {"$exists": True}},
        sort=[("timestamp", -1)],
        limit=1,
    )
    async for doc in cursor:
        full_content = doc.get("content", "")
    if full_content:
        print(full_content[:3000])

    print(f"\n{'='*80}")
    print("  ANALYSIS COMPLETE")
    print(f"{'='*80}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
