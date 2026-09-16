"""Provider registry for the SOCC energy library.

Each provider is a source of "fuel" (LLM inference). Only RF-accessible,
OpenAI-compatible providers are registered here by default — keys are your
own, dropped into the environment as disposable fuel.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str          # OpenAI-compatible /chat/completions base
    env_prefix: str        # keys read from <PREFIX>_1, <PREFIX>_2, ... or <PREFIX>
    default_model: str
    priority: int          # lower = preferred
    # rate window: how long a single key is cooled down after hitting a limit
    cooldown_seconds: int = 60
    rf_accessible: bool = True
    requires_key: bool = True   # local providers (Ollama) need no secret
    timeout: float = 30.0       # per-request; local cold-load needs more
    notes: str = ""
    # extra headers merged into every request (e.g. a client-gate User-Agent).
    # Empty for normal providers → no behaviour change.
    extra_headers: dict = field(default_factory=dict)


# Priority order = preference order when the router picks fuel.
REGISTRY: dict[str, Provider] = {
    "ollama": Provider(
        name="ollama",
        base_url="http://127.0.0.1:11434/v1",
        env_prefix="OLLAMA_KEY",          # unused; kept for uniformity
        default_model="jaahas/qwen3.5-uncensored:9b",
        priority=5,                        # local + free → preferred fuel
        cooldown_seconds=10,
        requires_key=False,
        timeout=180.0,                     # cold model load can be slow
        notes="Local models on your Mac. No key, no geo-block, no ban. Sovereign fuel.",
    ),
    "agentrouter": Provider(
        name="agentrouter",
        base_url="https://agentrouter.org/v1",
        env_prefix="AGENTROUTER_KEY",
        default_model="gpt-5.6-sol",          # also serves claude-opus-5 / claude-opus-4-8
        priority=8,                            # paid + reliable → above flaky free tiers, below local
        cooldown_seconds=60,
        timeout=60.0,                          # opus tier can be slow
        # Client-gate: a browser UA → 401 "unauthorized client detected". Must look like the CLI.
        extra_headers={"User-Agent": "claude-cli/1.0.60 (external, cli)", "x-app": "cli"},
        notes="TEXT relay (claude-opus-5 / gpt-5.6-sol). Paid, won't die on free-tier quota. No image models.",
    ),
    "openrouter": Provider(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        env_prefix="OPENROUTER_KEY",
        default_model="deepseek/deepseek-chat-v3.1:free",
        priority=10,
        cooldown_seconds=60,
        notes="One key, many free models. White-label aggregator.",
    ),
    "deepseek": Provider(
        name="deepseek",
        base_url="https://api.deepseek.com",
        env_prefix="DEEPSEEK_KEY",
        default_model="deepseek-chat",
        priority=20,
        cooldown_seconds=60,
        notes="Direct, RF-accessible.",
    ),
    "mistral": Provider(
        name="mistral",
        base_url="https://api.mistral.ai/v1",
        env_prefix="MISTRAL_KEY",
        default_model="mistral-small-latest",
        priority=30,
        cooldown_seconds=60,
        notes="Experiment free tier; phone needed at signup.",
    ),
    "huggingface": Provider(
        name="huggingface",
        base_url="https://router.huggingface.co/v1",
        env_prefix="HF_KEY",
        default_model="meta-llama/Llama-3.3-70B-Instruct",
        priority=40,
        cooldown_seconds=60,
        notes="Inference router, many open models.",
    ),
}


def by_priority() -> list[Provider]:
    return sorted(REGISTRY.values(), key=lambda p: p.priority)
