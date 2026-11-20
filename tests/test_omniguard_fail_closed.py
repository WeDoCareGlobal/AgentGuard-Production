"""Regression tests for fail-closed OmniGuard authorization."""
import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from agentguard import api
from agentguard.omniguard_client import OmniGuardDecision, OmniGuardResult


def _result(decision, **kwargs):
    return OmniGuardResult(
        decision=decision,
        confidence=1.0,
        signature="test",
        latency_ms=1.0,
        tier_latencies={},
        **kwargs,
    )


def _client(monkeypatch, result=None, error=None):
    client = Mock()
    client.inspect = AsyncMock(return_value=result) if error is None else AsyncMock(side_effect=error)
    monkeypatch.setattr(api, "OMNIGUARD_AVAILABLE", True)
    monkeypatch.setattr(api, "get_omniguard_client", lambda: client)


def test_missing_integration_fails_closed(monkeypatch):
    monkeypatch.setattr(api, "OMNIGUARD_AVAILABLE", False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api._omniguard_inspect("agent", "tool", {}))
    assert exc.value.status_code == 503


def test_inspection_error_fails_closed(monkeypatch):
    _client(monkeypatch, error=ConnectionError("offline"))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api._omniguard_inspect("agent", "tool", {}))
    assert exc.value.status_code == 503


def test_unknown_decision_fails_closed(monkeypatch):
    _client(monkeypatch, result=Mock(decision="UNKNOWN"))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api._omniguard_inspect("agent", "tool", {}))
    assert exc.value.status_code == 403


def test_allow_without_verified_signature_fails_closed(monkeypatch):
    _client(monkeypatch, result=_result(OmniGuardDecision.ALLOW))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api._omniguard_inspect("agent", "tool", {}))
    assert exc.value.status_code == 403


def test_explicit_block_is_rejected(monkeypatch):
    _client(monkeypatch, result=_result(OmniGuardDecision.BLOCK, blocked_reason="policy"))
    assert asyncio.run(api._omniguard_inspect("agent", "tool", {})) == "policy"
