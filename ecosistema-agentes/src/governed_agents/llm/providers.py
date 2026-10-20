"""Cerebros LLM para los agentes, gobernados como cualquier otra acción.

La integración no toca el orquestador: el proveedor se registra como una
herramienta más (``orchestrator.register_tool("llm.generate", ...)``) y
los agentes lo invocan con::

    context.act("llm.generate", f"model/{modelo}", {"prompt": ...}, cost=...)

Con ello las llamadas al modelo quedan sujetas a políticas (qué roles
pueden usar qué modelos, vía patrones sobre ``model/*``), a los límites
de presupuesto del agente y a la auditoría, sin ninguna vía de escape.

Se incluyen dos proveedores:

- :class:`MockLlmProvider`: determinista y sin red, para demos y pruebas.
- :class:`OpenAiCompatibleProvider`: cliente mínimo (solo stdlib) para
  cualquier API compatible con OpenAI (``/chat/completions``); toma la
  clave de un argumento o de la variable de entorno indicada.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from governed_agents.core.message import ActionRequest


@dataclass(frozen=True)
class LlmResponse:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LlmProvider(Protocol):
    def complete(self, model: str, prompt: str, **options: Any) -> LlmResponse: ...


@dataclass
class MockLlmProvider:
    """Proveedor determinista: útil sin credenciales ni red.

    ``canned`` permite fijar respuestas por fragmento de prompt; si nada
    coincide, devuelve un resumen sintético del prompt.
    """

    canned: dict[str, str] = field(default_factory=dict)

    def complete(self, model: str, prompt: str, **options: Any) -> LlmResponse:
        for fragment, response in self.canned.items():
            if fragment.lower() in prompt.lower():
                text = response
                break
        else:
            text = f"[respuesta simulada de {model}] Análisis del encargo: {prompt[:120]}"
        return LlmResponse(
            text=text,
            model=model,
            prompt_tokens=max(1, len(prompt.split())),
            completion_tokens=max(1, len(text.split())),
        )


@dataclass
class OpenAiCompatibleProvider:
    """Cliente mínimo para APIs compatibles con OpenAI (solo stdlib)."""

    base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    timeout: float = 60.0

    def _key(self) -> str:
        key = self.api_key or os.environ.get(self.api_key_env, "")
        if not key:
            raise RuntimeError(
                f"Falta la clave de API: defina {self.api_key_env} o pase api_key"
            )
        return key

    def build_request(self, model: str, prompt: str, **options: Any) -> urllib.request.Request:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            **options,
        }
        return urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._key()}",
            },
            method="POST",
        )

    def complete(self, model: str, prompt: str, **options: Any) -> LlmResponse:
        request = self.build_request(model, prompt, **options)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        usage = body.get("usage", {})
        return LlmResponse(
            text=body["choices"][0]["message"]["content"],
            model=body.get("model", model),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )


def create_llm_tool(provider: LlmProvider):
    """Adapta un proveedor LLM a la interfaz de herramienta del orquestador.

    Espera acciones ``llm.generate`` con recurso ``model/<nombre>`` y un
    parámetro ``prompt``; el resto de ``params`` se pasa al proveedor.
    """

    def executor(request: ActionRequest) -> dict[str, Any]:
        model = request.resource.removeprefix("model/")
        params = dict(request.params)
        prompt = params.pop("prompt")
        response = provider.complete(model, prompt, **params)
        return {
            "text": response.text,
            "model": response.model,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
        }

    return executor
