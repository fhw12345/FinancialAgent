"""Durable test-run budget; counts every forwarded inference attempt, never UI clicks."""

from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
import json
import asyncio
import hashlib
import time

import httpx
from pymongo import ReturnDocument

from src.core.exceptions import AppError
from src.services.copilot.protocol import CopilotError
from src.services.evidence.identity import digest
from src.shared.sanitizers import sanitize_text
from tests.model_portfolios.cases import case, manifest

CURRENT_CASE = ContextVar("portfolio_acceptance_case", default=None)
COLLECTION = "model_portfolio_acceptance_runs"


class BudgetStopped(AppError):
    status_code = 409
    error_type = "model_portfolio_budget_stopped"


class Budget:
    def __init__(self, db, run_id, mode):
        self.db, self.run_id, self.mode = db, run_id, mode
        self.collection = db.get_collection(COLLECTION)

    async def register(self):
        now = datetime.now(UTC)
        value = {
            "run_id": self.run_id,
            "mode": self.mode,
            "manifest": manifest(),
            "started_at": now.isoformat(),
            "deadline": (now + timedelta(seconds=600)).isoformat(),
            "revision": 0,
            "attempts": [],
            "results": [],
        }
        saved = await self.collection.find_one_and_update(
            {"_id": self.run_id},
            {"$setOnInsert": value},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if (
            saved is None
            or saved["manifest"] != manifest()
            or saved["mode"] != self.mode
        ):
            raise BudgetStopped("Run identity/manifest conflict; no allowance granted")
        return saved

    async def state(self):
        value = await self.collection.find_one({"_id": self.run_id})
        if value is None:
            raise BudgetStopped("Register the explicit test run first")
        return value

    async def reserve(self, identifier, body):
        selected = case(identifier)
        if selected.negative:
            raise BudgetStopped("Zero-call case cannot reserve inference")
        if (
            body.get("model") != "gpt-6-astra"
            or not isinstance(body.get("max_output_tokens"), int)
            or not 16 <= body["max_output_tokens"] <= 4096
        ):
            raise BudgetStopped("Model/token ceiling differs from authorized plan")
        state = await self.state()
        if datetime.now(UTC) >= datetime.fromisoformat(state["deadline"]):
            raise BudgetStopped("The authorized 10-minute run has expired")
        if len(state["attempts"]) >= 6 or any(
            a["case_id"] == identifier for a in state["attempts"]
        ):
            raise BudgetStopped("No automatic retry or allowance replenishment")
        attempt = {
            "case_id": identifier,
            "index": len(state["attempts"]) + 1,
            "model": body["model"],
            "max_output_tokens": body["max_output_tokens"],
            "request_hash": digest(body),
            "synthetic_prompt_input": sanitize_text(
                json.dumps(body.get("input", []), ensure_ascii=False)
            ),
            "provider_response_model": None,
            "started_at": datetime.now(UTC).isoformat(),
            "status": "reserved",
            "http_status": None,
            "latency_seconds": None,
            "usage": None,
            "response_hash": None,
            "structured_arguments": None,
        }
        result = await self.collection.find_one_and_update(
            {"_id": self.run_id, "revision": state["revision"]},
            {
                "$set": {
                    "attempts": [*state["attempts"], attempt],
                    "revision": state["revision"] + 1,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise BudgetStopped("Concurrent budget claim lost; nothing forwarded")
        return attempt

    async def complete(self, attempt, **details):
        # Test workers are serial, but a report observer/restart must not lose a budget event.
        for _ in range(10):
            state = await self.state()
            rows = [dict(a) for a in state["attempts"]]
            target = next(a for a in rows if a["index"] == attempt["index"])
            target.update(details)
            saved = await self.collection.find_one_and_update(
                {"_id": self.run_id, "revision": state["revision"]},
                {"$set": {"attempts": rows, "revision": state["revision"] + 1}},
                return_document=ReturnDocument.AFTER,
            )
            if saved:
                return
        raise BudgetStopped("Unable to durably finalize attempt")


class CapturedStream(httpx.AsyncByteStream):
    def __init__(self, stream, budget, attempt, status, started, deadline):
        self.stream, self.budget, self.attempt, self.http_status = (
            stream,
            budget,
            attempt,
            status,
        )
        self.chunks, self.started, self.ended = [], started, False
        self.deadline = deadline
        self.byte_count = 0

    async def __aiter__(self):
        async with asyncio.timeout(max(0, self.deadline - time.monotonic())):
            async for chunk in self.stream:
                self.chunks.append(chunk)
                self.byte_count += len(chunk)
                if self.byte_count > 2 * 1024 * 1024:
                    raise BudgetStopped("Provider stream exceeds bounded capture")
                yield chunk
            self.ended = True

    async def aclose(self):
        await self.stream.aclose()
        data = b"".join(self.chunks)
        usage, arguments, response_model = None, [], None
        for line in data.decode("utf-8", errors="replace").splitlines():
            if not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            response = event.get("response", {})
            if event.get("type") == "response.completed":
                response_model = response.get("model")
                raw_usage = response.get("usage", {})
                usage = {k: raw_usage.get(k) for k in ("input_tokens", "output_tokens")}
                arguments = [
                    sanitize_text(o.get("arguments", ""))
                    for o in response.get("output", [])
                    if o.get("type") == "function_call"
                ]
        await self.budget.complete(
            self.attempt,
            status="completed" if self.ended else "interrupted",
            http_status=self.http_status,
            latency_seconds=round(time.monotonic() - self.started, 4),
            usage=usage,
            response_hash=hashlib.sha256(data).hexdigest(),
            structured_arguments=arguments,
            provider_response_model=response_model,
        )


class GuardedTransport(httpx.AsyncBaseTransport):
    def __init__(self, budget, underlying, authorize):
        self.budget, self.underlying, self.authorize = budget, underlying, authorize

    async def handle_async_request(self, request):
        path, host = request.url.path, request.url.host
        if path == "/responses" and request.method == "POST":
            if request.url.scheme != "https" or host not in {
                "api.githubcopilot.com",
                "api.individual.githubcopilot.com",
                "api.business.githubcopilot.com",
                "api.enterprise.githubcopilot.com",
            }:
                raise BudgetStopped("Untrusted inference host")
            identifier = CURRENT_CASE.get()
            if identifier is None:
                raise BudgetStopped("Inference without a registered case is forbidden")
            self.authorize()
            attempt = await self.budget.reserve(identifier, json.loads(request.content))
            state = await self.budget.state()
            allowed_seconds = min(
                90,
                (
                    datetime.fromisoformat(state["deadline"]) - datetime.now(UTC)
                ).total_seconds(),
            )
            started = time.monotonic()
            deadline = started + max(0, allowed_seconds)
            try:
                async with asyncio.timeout(max(0, allowed_seconds)):
                    response = await self.underlying.handle_async_request(request)
            except BaseException:
                await self.budget.complete(attempt, status="transport_failed")
                raise
            return httpx.Response(
                response.status_code,
                headers=response.headers,
                stream=CapturedStream(
                    response.stream,
                    self.budget,
                    attempt,
                    response.status_code,
                    started,
                    deadline,
                ),
                request=request,
            )
        allowed = request.method == "GET" and (
            (host == "api.github.com" and path == "/copilot_internal/v2/token")
            or (
                host
                in {
                    "api.githubcopilot.com",
                    "api.individual.githubcopilot.com",
                    "api.business.githubcopilot.com",
                    "api.enterprise.githubcopilot.com",
                }
                and path == "/models"
            )
        )
        if not allowed:
            raise CopilotError("acceptance_external_request_not_allowlisted", 403)
        return await self.underlying.handle_async_request(request)

    async def aclose(self):
        # Copilot creates a client per request; do not destroy the shared guarded transport.
        pass
