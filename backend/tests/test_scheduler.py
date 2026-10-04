import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import Monitor, MonitorCheck
from app.monitoring.checker import CheckResult
from app.monitoring.scheduler import MonitorJob, due_monitors, is_due, persist_check, run_cycle, scheduler_loop

NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)


@pytest.mark.parametrize("interval", [30, 60, 300, 600])
def test_due_boundaries(interval):
    assert is_due(True, None, interval, NOW)
    assert not is_due(False, None, interval, NOW)
    assert not is_due(True, NOW - timedelta(seconds=interval - 1), interval, NOW)
    assert is_due(True, NOW - timedelta(seconds=interval), interval, NOW)
    assert not is_due(False, NOW - timedelta(days=1), interval, NOW)


def test_database_restart_and_pause(client, accounts, db):
    headers = accounts[0][1]
    created = client.post("/monitors", headers=headers, json={"name": "Test", "url": "https://example.com"}).json()
    sessions = sessionmaker(bind=db.bind)
    jobs = due_monitors(sessions, NOW)
    assert len(jobs) == 1
    db.add(MonitorCheck(monitor_id=uuid.UUID(created["id"]), status="UP", checked_at=NOW))
    db.commit()
    assert due_monitors(sessionmaker(bind=db.bind), NOW + timedelta(seconds=59)) == []
    assert len(due_monitors(sessionmaker(bind=db.bind), NOW + timedelta(seconds=60))) == 1
    client.patch('/monitors/' + created['id'], headers=headers, json={"is_active": False})
    assert due_monitors(sessions, NOW + timedelta(days=1)) == []
    assert not persist_check(sessions, jobs[0], CheckResult("DOWN"))
    client.patch('/monitors/' + created['id'], headers=headers, json={"is_active": True})
    assert persist_check(sessions, jobs[0], CheckResult("UP", 200, 10))
    db.expire_all()
    assert len(list(db.scalars(select(MonitorCheck)))) == 2
    client.delete('/monitors/' + created['id'], headers=headers)
    assert not persist_check(sessions, jobs[0], CheckResult("UP"))
    assert list(db.scalars(select(MonitorCheck))) == []


def test_concurrency_and_individual_failures(monkeypatch):
    import app.monitoring.scheduler as scheduler
    jobs = [MonitorJob(uuid.uuid4(), str(i), 10, 30) for i in range(12)]
    monkeypatch.setattr(scheduler, "due_monitors", lambda *args: jobs)
    monkeypatch.setattr(scheduler, "still_active", lambda *args: True)
    saved = []
    monkeypatch.setattr(scheduler, "persist_check", lambda sessions, job, result: saved.append(result))
    active = peak = 0
    async def checker(client, url, *args):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.001)
        active -= 1
        if url == "3":
            raise RuntimeError("isolated")
        return CheckResult("UP" if url == "1" else "DOWN", error_type=None if url == "1" else "timeout")
    monkeypatch.setattr(scheduler, "check_http", checker)
    asyncio.run(run_cycle(None, None, 3, 5))
    assert peak == 3 and len(saved) == 11
    assert any(result.status == "UP" for result in saved)


def test_real_checker_resilience(monkeypatch):
    import app.monitoring.scheduler as scheduler
    from app.monitoring.checker import check_http
    jobs = [MonitorJob(uuid.uuid4(), f"https://example.com/{i}", 1, 30) for i in range(3)]
    monkeypatch.setattr(scheduler, "due_monitors", lambda *args: jobs)
    monkeypatch.setattr(scheduler, "still_active", lambda *args: True)
    saved = {}
    monkeypatch.setattr(scheduler, "persist_check", lambda sessions, job, result: saved.update({job.url: result}))
    async def checker(client, url, timeout, redirects):
        return await check_http(client, url, timeout, redirects, AsyncMock(return_value=["93.184.216.34"]))
    monkeypatch.setattr(scheduler, "check_http", checker)
    def handler(request):
        if request.url.path == "/0":
            raise httpx.ReadTimeout("timeout")
        if request.url.path == "/2":
            raise httpx.ConnectError("failure")
        return httpx.Response(200)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await run_cycle(None, client, 2, 5)
    asyncio.run(run())
    assert [saved[j.url].status for j in jobs] == ["DOWN", "UP", "DOWN"]


def test_loop_recovers_after_database_error(monkeypatch):
    import app.monitoring.scheduler as scheduler
    async def run():
        stop = asyncio.Event()
        calls = 0
        async def cycle(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("database unavailable")
            stop.set()
        monkeypatch.setattr(scheduler, "run_cycle", cycle)
        await scheduler_loop(None, None, stop, 2, 0.001, 5)
        assert calls == 2
    asyncio.run(run())


def test_save_failure_does_not_cancel_others(monkeypatch):
    import app.monitoring.scheduler as scheduler
    jobs = [MonitorJob(uuid.uuid4(), "https://example.com", 1, 30) for _ in range(3)]
    monkeypatch.setattr(scheduler, "due_monitors", lambda *args: jobs)
    monkeypatch.setattr(scheduler, "still_active", lambda *args: True)
    monkeypatch.setattr(scheduler, "check_http", AsyncMock(return_value=CheckResult("UP")))
    saved = []
    def persist(sessions, job, result):
        if job == jobs[0]:
            raise RuntimeError("save failed")
        saved.append(job)
    monkeypatch.setattr(scheduler, "persist_check", persist)
    asyncio.run(run_cycle(None, None, 1, 5))
    assert saved == jobs[1:]
