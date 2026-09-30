"""Office posting replicas insert new subjects and update existing subjects atomically."""
import asyncio

import pytest
from sqlalchemy import Column, MetaData, String, Table, insert, select

from epfo_persistence.consumer import apply_once
from epfo_persistence.postings import apply_posting
from test_persistence import sessions  # noqa: F401 (fixture)


@pytest.fixture
def office_staff(sessions):
    table = Table("office_staff", MetaData(), Column("subject", String, primary_key=True),
                  Column("stakeholder", String, nullable=False), Column("office_id", String, nullable=False))

    async def setup():
        async with sessions.kw["bind"].begin() as connection:
            await connection.run_sync(table.metadata.create_all)
    asyncio.run(setup())
    return table


def test_posting_inserts_and_updates_without_touching_other_staff(sessions, office_staff):
    async def run():
        async with sessions() as session, session.begin():
            await session.execute(insert(office_staff).values(subject="other", stakeholder="fo.oic", office_id="RO-01"))
            await apply_posting(session, {"payload": {"subject": "officer", "stakeholder": "fo.pro", "office_id": "RO-01"}}, office_staff)
        async with sessions() as session:
            assert dict((await session.execute(select(office_staff).where(office_staff.c.subject == "officer"))).mappings().one()) == {
                "subject": "officer", "stakeholder": "fo.pro", "office_id": "RO-01"}
        event = {"event_id": "posting-1", "event_type": "StaffPostingChanged.v1",
                 "payload": {"subject": "officer", "stakeholder": "fo.apfc", "office_id": "RO-02"}}

        async def handler(session, delivered):
            await apply_posting(session, delivered, office_staff)
        assert await apply_once(sessions, event, handler) is True
        assert await apply_once(sessions, event, handler) is False
        assert await apply_once(sessions, {**event, "event_id": "posting-2"}, handler) is True
        async with sessions() as session:
            rows = (await session.execute(select(office_staff).order_by(office_staff.c.subject))).mappings().all()
        assert [dict(r) for r in rows] == [
            {"subject": "officer", "stakeholder": "fo.apfc", "office_id": "RO-02"},
            {"subject": "other", "stakeholder": "fo.oic", "office_id": "RO-01"},
        ]
    asyncio.run(run())


def test_posting_rolls_back_with_its_callers_transaction(sessions, office_staff):
    async def run():
        async with sessions() as session, session.begin():
            await session.execute(insert(office_staff).values(subject="officer", stakeholder="fo.pro", office_id="RO-01"))
        with pytest.raises(RuntimeError, match="abort"):
            async with sessions() as session, session.begin():
                await apply_posting(session, {"payload": {"subject": "officer", "stakeholder": "fo.apfc", "office_id": "RO-02"}}, office_staff)
                await apply_posting(session, {"payload": {"subject": "new", "stakeholder": "fo.pro", "office_id": "RO-02"}}, office_staff)
                raise RuntimeError("abort")
        async with sessions() as session:
            rows = (await session.execute(select(office_staff))).mappings().all()
        assert [dict(r) for r in rows] == [{"subject": "officer", "stakeholder": "fo.pro", "office_id": "RO-01"}]
    asyncio.run(run())
