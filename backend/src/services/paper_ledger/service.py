"""Manual PAPER operations and on-demand valuation. No research/approval/real-ledger writes."""

from datetime import UTC, datetime

from ...database.repositories.evidence_repository import EvidenceStorage
from ...models.paper_ledger import (
    CreatePaper,
    JournalPaper,
    PaperExperiment,
    PaperRequest,
    PaperSettings,
    PaperTradeReceipt,
    PaperView,
    RefreshPaper,
    TradeInput,
)
from ...models.portfolio_risk import Record
from ..evidence.identity import digest
from ..portfolio_risk.calendar import completed_session, next_close
from . import store, valuation
from .accounting import replay, trade_amounts


class PaperSummary(Record):
    experiment_id: str
    name: str
    sequence: int
    closed: bool


def view(current: PaperExperiment) -> PaperView:
    settings, projection = replay(current.events)
    receipts = []
    for row in current.events:
        if isinstance(row.payload, TradeInput):
            effective, principal, commission = trade_amounts(settings, row.payload)
            receipts.append(
                PaperTradeReceipt(
                    event_id=row.event_id,
                    effective_price=effective,
                    principal=principal,
                    commission=commission,
                )
            )
    return PaperView(
        experiment=current,
        settings=settings,
        projection=projection,
        valuation=valuation.receipt(current.events),
        current_session=completed_session(datetime.now(UTC)),
        trade_receipts=receipts,
    )


async def create(db: EvidenceStorage, body: CreatePaper) -> PaperView:
    return view(await store.create(db, body))


async def get(db: EvidenceStorage, identifier: str) -> PaperView:
    return view(await store.get(db, identifier))


async def recent(db: EvidenceStorage) -> list[PaperSummary]:
    rows = []
    async for row in (
        db.get_collection(store.COLLECTION).find({}).sort("_id", -1).limit(50)
    ):
        current = store.parse(row)
        settings, projection = replay(current.events)
        rows.append(
            PaperSummary(
                experiment_id=current.experiment_id,
                name=settings.name,
                sequence=current.sequence,
                closed=projection.closed,
            )
        )
    return rows


def writable(current: PaperExperiment, body: PaperRequest) -> PaperSettings:
    settings, projection = replay(current.events)
    if body.expected_sequence != current.sequence:
        raise store.PaperConflict("Paper ledger changed; reload before recording")
    if projection.closed:
        raise store.PaperConflict("Paper experiment is closed; history is read-only")
    return settings


async def journal(
    db: EvidenceStorage, identifier: str, body: JournalPaper
) -> PaperView:
    current = await store.get(db, identifier)
    fingerprint = digest(body.model_dump(mode="json"))
    if store.replay_request(current, body.request_id, fingerprint):
        return view(current)
    writable(current, body)
    addition = store.event(
        identifier,
        current.sequence + 1,
        body.request_id,
        fingerprint,
        body.entry,
        current.events[-1].event_hash,
    )
    return view(await store.append(db, current, addition))


async def refresh(
    db: EvidenceStorage, identifier: str, body: RefreshPaper
) -> PaperView:
    current = await store.get(db, identifier)
    fingerprint = digest(body.model_dump(mode="json"))
    if store.replay_request(current, body.request_id, fingerprint):
        return view(current)
    writable(current, body)
    now = datetime.now(UTC)
    if body.session_date != completed_session(now):
        raise store.PaperConflict(
            "Valuation must use the current completed XNYS session"
        )
    _, projection = replay(current.events)
    payload = await valuation.capture(projection, current.sequence, body.session_date)
    if body.session_date != completed_session(datetime.now(UTC)):
        raise store.PaperConflict("Session changed during valuation; refresh again")
    addition = store.event(
        identifier,
        current.sequence + 1,
        body.request_id,
        fingerprint,
        payload,
        current.events[-1].event_hash,
    )
    return view(
        await store.append(db, current, addition, next_close(body.session_date))
    )
