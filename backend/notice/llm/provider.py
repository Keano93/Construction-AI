"""LLM providers.

* ClaudeProvider — Anthropic Claude via the official SDK, structured outputs
  validated against Pydantic schemas. The only external service Notice talks to.
* OfflineProvider — deterministic, rule-based handlers registered per task.
  Lets the platform, tests and evals run with no network or API key, and gives
  a baseline the Claude path must beat in the eval.

Selection: NOTICE_LLM_PROVIDER = auto | claude | offline. `auto` uses Claude
when ANTHROPIC_API_KEY is set, otherwise offline.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from ..config import get_settings
from .prompts import Prompt

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    output: BaseModel
    provider: str
    model: str | None
    usage: dict = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str
    model: str | None

    def structured(self, *, task: str, prompt: Prompt, variables: dict[str, Any], schema: type[T], max_tokens: int = 16000) -> LLMResult: ...


# --- Claude --------------------------------------------------------------

class ClaudeProvider:
    name = "claude"

    def __init__(self, model: str | None = None, effort: str | None = None) -> None:
        import anthropic

        s = get_settings()
        self.model = model or s.claude_model
        self.effort = effort or s.claude_effort
        self.use_fallbacks = s.claude_server_fallbacks
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(max_retries=3)

    def structured(self, *, task: str, prompt: Prompt, variables: dict[str, Any], schema: type[T], max_tokens: int = 16000) -> LLMResult:
        anthropic = self._anthropic
        system, user = prompt.render(**variables)
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            output_config={"effort": self.effort},
        )
        if self.use_fallbacks:
            # Server-side refusal fallback: if the model declines, the API re-runs on a fallback model.
            kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        try:
            resp = self.client.beta.messages.parse(**kwargs)
        except anthropic.BadRequestError as e:
            raise LLMError(f"Claude rejected request for {task}: {e.message}") from e
        except anthropic.RateLimitError as e:
            raise LLMError(f"Claude rate limited ({task}); retry later") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude API error {e.status_code} for {task}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(f"Could not reach Claude API for {task}") from e

        if resp.stop_reason == "refusal":
            raise LLMError(f"Claude declined task {task}")
        if resp.stop_reason == "max_tokens":
            raise LLMError(f"Output truncated for {task}; raise max_tokens")
        if resp.parsed_output is None:
            raise LLMError(f"No structured output for {task}")
        usage = {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "request_id": getattr(resp, "_request_id", None),
            "served_model": resp.model,
        }
        return LLMResult(output=resp.parsed_output, provider=self.name, model=resp.model, usage=usage)


# --- Offline -------------------------------------------------------------

OfflineHandler = Callable[[dict[str, Any]], BaseModel]
_OFFLINE: dict[str, OfflineHandler] = {}


def offline_handler(task: str) -> Callable[[OfflineHandler], OfflineHandler]:
    def deco(fn: OfflineHandler) -> OfflineHandler:
        _OFFLINE[task] = fn
        return fn

    return deco


class OfflineProvider:
    name = "offline"
    model = "rules-v1"

    def structured(self, *, task: str, prompt: Prompt, variables: dict[str, Any], schema: type[T], max_tokens: int = 16000) -> LLMResult:
        if task not in _OFFLINE:
            raise LLMError(f"No offline handler registered for task '{task}'")
        out = _OFFLINE[task](variables)
        return LLMResult(output=schema.model_validate(out.model_dump()), provider=self.name, model=self.model)


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        choice = get_settings().llm_provider
        if choice == "claude" or (choice == "auto" and os.environ.get("ANTHROPIC_API_KEY")):
            _provider = ClaudeProvider()
        else:
            _provider = OfflineProvider()
        log.info("LLM provider: %s", _provider.name)
    return _provider


def set_provider(p: LLMProvider | None) -> None:
    global _provider
    _provider = p
