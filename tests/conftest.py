import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_ai_response():
    """Create a mock LiteLLM response object."""
    response = MagicMock()
    response.choices = [
        MagicMock(message=MagicMock(content="I'm Signal, ready to help!"))
    ]
    response.usage = MagicMock(prompt_tokens=20, completion_tokens=30)
    response.model = "anthropic/claude-sonnet-4-20250514"
    return response
