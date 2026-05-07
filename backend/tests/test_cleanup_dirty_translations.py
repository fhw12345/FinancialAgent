"""Tests for cleanup_dirty_translations script.

Strategy: mock the motor collection with ``AsyncMock`` so tests do not need
a live mongod. We verify (a) the query shape passed to ``find``, (b) the
update payload passed to ``update_many``, and (c) dry-run does not write.
A small in-memory async cursor stand-in lets us exercise ``scan_dirty``'s
``async for`` loop end-to-end on flat and nested ``metadata.*`` docs.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.cleanup_dirty_translations import (
    build_dirty_query,
    cleanup_one,
    scan_dirty,
)


class _FakeCursor:
    """Minimal async cursor: supports ``async for``."""

    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = list(docs)

    def __aiter__(self) -> "_FakeCursor":
        self._iter = iter(self._docs)
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            return next(self._iter)
        except StopIteration as e:
            raise StopAsyncIteration from e


def _make_coll(docs: list[dict[str, Any]], name: str = "messages") -> MagicMock:
    coll = MagicMock()
    coll.name = name
    # ``find`` is sync on motor and returns a cursor.
    coll.find = MagicMock(return_value=_FakeCursor(docs))
    coll.update_many = AsyncMock(
        return_value=MagicMock(matched_count=0, modified_count=0)
    )
    return coll


def test_build_dirty_query_shape() -> None:
    q = build_dirty_query("content", "content_zh")
    assert "$expr" in q
    expr = q["$expr"]["$and"]
    assert {"$ne": ["$content_zh", None]} in expr
    assert {"$ne": ["$content_zh", ""]} in expr
    assert {"$eq": ["$content_zh", "$content"]} in expr


def test_build_dirty_query_dotted_path() -> None:
    q = build_dirty_query("metadata.reasoning", "metadata.reasoning_zh")
    expr = q["$expr"]["$and"]
    assert {"$eq": ["$metadata.reasoning_zh", "$metadata.reasoning"]} in expr


@pytest.mark.asyncio
async def test_scan_dirty_finds_equal_fields() -> None:
    docs = [
        {"_id": "A", "content": "Hello", "content_zh": "Hello"},
        {"_id": "B", "content": "Hello", "content_zh": "你好"},
        {"_id": "C", "content": "Hello", "content_zh": None},
    ]
    # The fake cursor doesn't actually filter — that's the server's job. We
    # pre-filter to mimic what mongo would return for the query.
    server_filtered = [docs[0]]
    coll = _make_coll(server_filtered)
    result = await scan_dirty(coll, "content", "content_zh")
    assert len(result) == 1
    assert result[0]["_id"] == "A"
    assert result[0]["en_len"] == 5
    assert result[0]["zh_len"] == 5
    # And confirm find() was called with a $expr query.
    args, _ = coll.find.call_args
    assert "$expr" in args[0]


@pytest.mark.asyncio
async def test_cleanup_one_dry_run_does_not_modify() -> None:
    coll = _make_coll([{"_id": "A", "content": "Hi", "content_zh": "Hi"}])
    n = await cleanup_one(coll, "content", "content_zh", dry_run=True)
    assert n == 1
    coll.update_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_one_apply_sets_null() -> None:
    coll = _make_coll([{"_id": "A", "content": "Hi", "content_zh": "Hi"}])
    coll.update_many.return_value = MagicMock(matched_count=1, modified_count=1)
    n = await cleanup_one(coll, "content", "content_zh", dry_run=False)
    assert n == 1
    coll.update_many.assert_awaited_once()
    call_args = coll.update_many.await_args
    filt, update = call_args.args
    assert filt == {"_id": {"$in": ["A"]}}
    assert update == {"$set": {"content_zh": None}}


@pytest.mark.asyncio
async def test_cleanup_one_no_dirty_skips_update() -> None:
    coll = _make_coll([])
    n = await cleanup_one(coll, "content", "content_zh", dry_run=False)
    assert n == 0
    coll.update_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_nested_metadata_path_scan_and_update() -> None:
    nested = [
        {
            "_id": "X",
            "metadata": {"reasoning": "Because X", "reasoning_zh": "Because X"},
        }
    ]
    coll = _make_coll(nested, name="portfolio_orders")
    coll.update_many.return_value = MagicMock(matched_count=1, modified_count=1)

    found = await scan_dirty(coll, "metadata.reasoning", "metadata.reasoning_zh")
    assert len(found) == 1
    assert found[0]["en_len"] == len("Because X")
    assert found[0]["zh_len"] == len("Because X")

    # Re-prime cursor for the second pass inside cleanup_one.
    coll.find = MagicMock(return_value=_FakeCursor(nested))
    n = await cleanup_one(
        coll, "metadata.reasoning", "metadata.reasoning_zh", dry_run=False
    )
    assert n == 1
    _, update = coll.update_many.await_args.args
    assert update == {"$set": {"metadata.reasoning_zh": None}}
