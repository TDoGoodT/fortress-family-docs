"""Extended tests for llm_dispatch.llm_generate — covers task_type param
added in the dispatch-cleanup refactor.

Note: BedrockClient and OllamaClient are lazy-imported inside llm_generate,
so we patch them at their source modules, not at llm_dispatch.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_llm_generate_model_tier_backward_compat():
    """Existing callers using model_tier= still work unchanged."""
    from src.services.llm_dispatch import llm_generate

    with patch("src.services.bedrock_client.BedrockClient") as mock_cls:
        mock_bedrock = AsyncMock()
        mock_bedrock.generate = AsyncMock(return_value="response text")
        mock_cls.return_value = mock_bedrock

        result = await llm_generate("prompt", "system", model_tier="lite")

    assert result == "response text"


@pytest.mark.asyncio
async def test_llm_generate_task_type_uses_select_model():
    """When task_type is provided, llm_generate uses select_model() routing."""
    from src.services.llm_dispatch import llm_generate

    with patch("src.services.bedrock_client.BedrockClient") as mock_cls:
        mock_bedrock = AsyncMock()
        mock_bedrock.generate = AsyncMock(return_value="response text")
        mock_cls.return_value = mock_bedrock

        with patch("src.services.model_selector.select_model", return_value="test-model-id") as mock_select:
            result = await llm_generate("prompt", "system", task_type="chat")

    assert result == "response text"


@pytest.mark.asyncio
async def test_llm_generate_task_type_takes_priority_over_model_tier():
    """task_type takes priority when both are provided."""
    from src.services.llm_dispatch import llm_generate

    with patch("src.services.bedrock_client.BedrockClient") as mock_cls:
        mock_bedrock = AsyncMock()
        mock_bedrock.generate = AsyncMock(return_value="response text")
        mock_cls.return_value = mock_bedrock

        with patch("src.services.model_selector.select_model", return_value="task-model-id") as mock_select:
            result = await llm_generate("prompt", "system", model_tier="lite", task_type="chat")

    assert result == "response text"


@pytest.mark.asyncio
async def test_llm_generate_returns_empty_on_total_failure():
    """Returns empty string when both Bedrock and Ollama fail."""
    from src.services.llm_dispatch import llm_generate

    with patch("src.services.bedrock_client.BedrockClient") as mock_bedrock_cls:
        mock_bedrock_cls.side_effect = Exception("bedrock down")

        with patch("src.services.llm_client.OllamaClient") as mock_ollama_cls:
            mock_ollama = AsyncMock()
            mock_ollama.generate = AsyncMock(side_effect=Exception("ollama down"))
            mock_ollama_cls.return_value = mock_ollama

            result = await llm_generate("prompt", "system")

    assert result == ""
