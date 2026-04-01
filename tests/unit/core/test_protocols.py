"""Tests for core protocol definitions."""

import pytest
from unittest.mock import AsyncMock

from signalagent.core.protocols import AILayerProtocol


class TestAILayerProtocol:
    def test_async_mock_satisfies_protocol(self):
        """An AsyncMock with the right shape satisfies the protocol."""
        mock = AsyncMock()
        mock.complete = AsyncMock()
        assert isinstance(mock, AILayerProtocol)

    def test_object_without_complete_fails(self):
        class Bad:
            pass
        assert not isinstance(Bad(), AILayerProtocol)
