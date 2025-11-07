from __future__ import annotations

from typing import Optional, Dict, Iterable
import ollama

from app.core.config import get_settings
from app.domain.ports import LLMPort


class OllamaLLM(LLMPort):
    def __init__(self, model: Optional[str] = None,
                 temperature: Optional[float] = None,
                 top_p: Optional[float] = None,
                 seed: Optional[int] = None):
        settings = get_settings()
        self.model = model or settings.ollama_model
        # opções padrão configuráveis via Settings / .env
        self._default_options = {
            'temperature': temperature if temperature is not None else settings.llm_temperature,
            'top_p': top_p if top_p is not None else settings.llm_top_p,
            'seed': seed if seed is not None else settings.llm_seed,
        }

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        options: Optional[Dict[str, any]] = None,
    ) -> str:
        msgs = []
        if system_prompt:
            msgs.append({'role': 'system', 'content': system_prompt})
        msgs.append({'role': 'user', 'content': prompt})
        response = ollama.chat(
            model=self.model,
            messages=msgs,
            options={**self._default_options, **(options or {})},
        )
        return response['message']['content']

    def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        options: Optional[Dict[str, any]] = None,
    ) -> Iterable[str]:
        msgs = []
        if system_prompt:
            msgs.append({'role': 'system', 'content': system_prompt})
        msgs.append({'role': 'user', 'content': prompt})
        for part in ollama.chat(
            model=self.model,
            messages=msgs,
            options={**self._default_options, **(options or {})},
            stream=True,
        ):
            piece = (part.get('message') or {}).get('content')
            if piece:
                yield piece
