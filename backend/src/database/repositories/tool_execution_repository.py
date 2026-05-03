"""
Tool execution repository for tracking all tool calls.

Stores execution records for both 1st-party and 3rd-party (MCP) tools.
"""

from datetime import datetime
from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorCollection

from ...models.tool_execution import ToolExecution

logger = structlog.get_logger()


class ToolExecutionRepository:
    """Repository for tool execution data access operations."""

    def __init__(self, collection: AsyncIOMotorCollection):
        """
        Initialize tool execution repository.

        Args:
            collection: MongoDB collection for tool_executions
        """
        self.collection = collection

    async def ensure_indexes(self) -> None:
        """Create indexes for optimal query performance."""
        await self.collection.create_index(
            [("analysis_id", 1), ("started_at", 1)], name="idx_analysis_tools"
        )
        await self.collection.create_index(
            [("chat_id", 1), ("started_at", -1)], name="idx_chat_tools"
        )
        await self.collection.create_index(
            [("started_at", -1)], name="idx_started_at"
        )
        await self.collection.create_index(
            [("tool_source", 1), ("is_paid_api", 1)], name="idx_tool_cost"
        )
        logger.info("Tool execution indexes ensured")

    async def create(self, execution: ToolExecution) -> ToolExecution:
        """
        Create a new tool execution record.

        Args:
            execution: Tool execution data

        Returns:
            Created tool execution
        """
        # Convert to dict for MongoDB
        execution_dict = execution.model_dump()

        # Insert into database
        await self.collection.insert_one(execution_dict)

        logger.info(
            "Tool execution created",
            execution_id=execution.execution_id,
            tool_name=execution.tool_name,
            tool_source=execution.tool_source,
            status=execution.status,
        )

        return execution

    async def get(self, execution_id: str) -> ToolExecution | None:
        """
        Get tool execution by ID.

        Args:
            execution_id: Execution identifier

        Returns:
            ToolExecution if found, None otherwise
        """
        execution_dict = await self.collection.find_one({"execution_id": execution_id})

        if not execution_dict:
            return None

        # Remove MongoDB _id field
        execution_dict.pop("_id", None)

        return ToolExecution(**execution_dict)

    async def list_by_analysis(
        self, analysis_id: str, limit: int = 100
    ) -> list[ToolExecution]:
        """
        List all tool executions for an analysis workflow.

        Used for audit trail and cost tracking.

        Args:
            analysis_id: Analysis workflow ID
            limit: Maximum number of executions to return

        Returns:
            List of tool executions sorted by started_at ascending
        """
        cursor = (
            self.collection.find({"analysis_id": analysis_id})
            .sort("started_at", 1)
            .limit(limit)
        )

        executions = []
        async for execution_dict in cursor:
            # Remove MongoDB _id field
            execution_dict.pop("_id", None)
            executions.append(ToolExecution(**execution_dict))

        return executions

    async def list_by_chat(self, chat_id: str, limit: int = 100) -> list[ToolExecution]:
        """
        List all tool executions for a chat.

        Args:
            chat_id: Chat identifier
            limit: Maximum number of executions to return

        Returns:
            List of tool executions sorted by started_at descending
        """
        cursor = (
            self.collection.find({"chat_id": chat_id})
            .sort("started_at", -1)
            .limit(limit)
        )

        executions = []
        async for execution_dict in cursor:
            # Remove MongoDB _id field
            execution_dict.pop("_id", None)
            executions.append(ToolExecution(**execution_dict))

        return executions

    async def get_cost_summary(
        self,
        user_id: str | None = None,
        start_date: datetime = None,
        end_date: datetime = None,
    ) -> dict[str, Any]:
        """Get cost summary within date range. user_id ignored."""
        pipeline = [
            {
                "$match": {
                    "started_at": {"$gte": start_date, "$lte": end_date},
                }
            },
            {
                "$group": {
                    "_id": "$tool_source",
                    "total_calls": {"$sum": 1},
                    "total_cost": {"$sum": "$api_cost"},
                    "cache_hits": {"$sum": {"$cond": ["$cache_hit", 1, 0]}},
                    "successful_calls": {
                        "$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}
                    },
                }
            },
        ]

        results = await self.collection.aggregate(pipeline).to_list(100)

        # Aggregate results
        total_executions = sum(r["total_calls"] for r in results)
        total_cost = sum(r["total_cost"] for r in results)
        total_cache_hits = sum(r["cache_hits"] for r in results)

        by_tool_source = {
            r["_id"]: {
                "calls": r["total_calls"],
                "cost": r["total_cost"],
                "cache_hits": r["cache_hits"],
                "successful_calls": r["successful_calls"],
            }
            for r in results
        }

        return {
            "total_executions": total_executions,
            "total_cost": total_cost,
            "cache_hit_rate": (
                total_cache_hits / total_executions if total_executions > 0 else 0.0
            ),
            "by_tool_source": by_tool_source,
        }

    async def get_tool_performance_metrics(
        self, start_date: datetime, end_date: datetime, limit: int = 50
    ) -> dict[str, Any]:
        """
        Get tool execution performance metrics aggregated by tool name.

        Used for baseline performance measurement and optimization tracking.

        Args:
            start_date: Start datetime for analysis period
            end_date: End datetime for analysis period
            limit: Maximum number of tools to return

        Returns:
            Performance metrics dict:
            {
                "period": {"start": ..., "end": ...},
                "summary": {
                    "total_executions": 1000,
                    "avg_duration_ms": 1250,
                    "success_rate": 0.98,
                    "cache_hit_rate": 0.75
                },
                "by_tool": [
                    {
                        "tool_name": "GLOBAL_QUOTE",
                        "tool_source": "mcp_alphavantage",
                        "total_calls": 500,
                        "avg_duration_ms": 1200,
                        "p50_duration_ms": 1100,
                        "p95_duration_ms": 2500,
                        "p99_duration_ms": 3500,
                        "success_rate": 0.99,
                        "cache_hit_rate": 0.80
                    },
                    ...
                ]
            }
        """
        # Aggregation pipeline for tool performance
        pipeline = [
            {
                "$match": {
                    "started_at": {"$gte": start_date, "$lte": end_date},
                    "duration_ms": {"$exists": True, "$ne": None},
                }
            },
            {
                "$group": {
                    "_id": {"tool_name": "$tool_name", "tool_source": "$tool_source"},
                    "total_calls": {"$sum": 1},
                    "avg_duration_ms": {"$avg": "$duration_ms"},
                    "min_duration_ms": {"$min": "$duration_ms"},
                    "max_duration_ms": {"$max": "$duration_ms"},
                    "durations": {"$push": "$duration_ms"},
                    "successful_calls": {
                        "$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}
                    },
                    "cache_hits": {"$sum": {"$cond": ["$cache_hit", 1, 0]}},
                }
            },
            {"$sort": {"total_calls": -1}},
            {"$limit": limit},
        ]

        results = await self.collection.aggregate(pipeline).to_list(limit)

        # Calculate percentiles and format results
        by_tool = []
        total_executions = 0
        total_duration_sum = 0
        total_successful = 0
        total_cache_hits = 0

        for r in results:
            durations = sorted(r["durations"])
            count = len(durations)

            # Calculate percentiles
            p50_idx = int(count * 0.50)
            p95_idx = int(count * 0.95)
            p99_idx = int(count * 0.99)

            p50 = durations[min(p50_idx, count - 1)] if count > 0 else 0
            p95 = durations[min(p95_idx, count - 1)] if count > 0 else 0
            p99 = durations[min(p99_idx, count - 1)] if count > 0 else 0

            tool_metrics = {
                "tool_name": r["_id"]["tool_name"],
                "tool_source": r["_id"]["tool_source"],
                "total_calls": r["total_calls"],
                "avg_duration_ms": round(r["avg_duration_ms"], 2),
                "min_duration_ms": r["min_duration_ms"],
                "max_duration_ms": r["max_duration_ms"],
                "p50_duration_ms": p50,
                "p95_duration_ms": p95,
                "p99_duration_ms": p99,
                "success_rate": round(
                    (
                        r["successful_calls"] / r["total_calls"]
                        if r["total_calls"] > 0
                        else 0
                    ),
                    4,
                ),
                "cache_hit_rate": round(
                    r["cache_hits"] / r["total_calls"] if r["total_calls"] > 0 else 0,
                    4,
                ),
            }
            by_tool.append(tool_metrics)

            # Accumulate totals
            total_executions += r["total_calls"]
            total_duration_sum += r["avg_duration_ms"] * r["total_calls"]
            total_successful += r["successful_calls"]
            total_cache_hits += r["cache_hits"]

        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "summary": {
                "total_executions": total_executions,
                "avg_duration_ms": round(
                    (
                        total_duration_sum / total_executions
                        if total_executions > 0
                        else 0
                    ),
                    2,
                ),
                "success_rate": round(
                    total_successful / total_executions if total_executions > 0 else 0,
                    4,
                ),
                "cache_hit_rate": round(
                    total_cache_hits / total_executions if total_executions > 0 else 0,
                    4,
                ),
            },
            "by_tool": by_tool,
        }

    async def get_slowest_tools(
        self, start_date: datetime, end_date: datetime, limit: int = 10
    ) -> list[dict[str, Any]]:
        """
        Get the slowest tools by average execution time.

        Used to identify optimization targets.

        Args:
            start_date: Start datetime
            end_date: End datetime
            limit: Number of tools to return

        Returns:
            List of tools sorted by avg_duration_ms descending
        """
        pipeline = [
            {
                "$match": {
                    "started_at": {"$gte": start_date, "$lte": end_date},
                    "duration_ms": {"$exists": True, "$ne": None},
                    "status": "success",  # Only successful executions
                }
            },
            {
                "$group": {
                    "_id": {"tool_name": "$tool_name", "tool_source": "$tool_source"},
                    "total_calls": {"$sum": 1},
                    "avg_duration_ms": {"$avg": "$duration_ms"},
                    "max_duration_ms": {"$max": "$duration_ms"},
                }
            },
            {"$match": {"total_calls": {"$gte": 5}}},  # Min 5 calls for significance
            {"$sort": {"avg_duration_ms": -1}},
            {"$limit": limit},
        ]

        results = await self.collection.aggregate(pipeline).to_list(limit)

        return [
            {
                "tool_name": r["_id"]["tool_name"],
                "tool_source": r["_id"]["tool_source"],
                "total_calls": r["total_calls"],
                "avg_duration_ms": round(r["avg_duration_ms"], 2),
                "max_duration_ms": r["max_duration_ms"],
            }
            for r in results
        ]
