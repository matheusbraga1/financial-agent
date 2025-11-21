from typing import Optional, Iterator
import json
import logging
import time

import requests

from app.infrastructure.logging import StructuredLogger

logger = logging.getLogger(__name__)
structured_logger = StructuredLogger(__name__)

class OllamaAdapter:
    """Adapter for Ollama LLM API integration."""

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "qwen2.5:3b",
        temperature: float = 0.2,
        top_p: float = 0.9,
        timeout: int = 120,
        max_tokens: int = 2048,
    ):
        self.host = host.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.model_name = f"ollama/{model}"
        self.is_available = False

        self._check_availability()

        logger.info(
            f"OllamaAdapter inicializado: host={host}, modelo={model}, "
            f"max_tokens={max_tokens}, disponível={'✓' if self.is_available else '✗'}"
        )

    def _check_availability(self) -> None:
        try:
            response = requests.get(
                f"{self.host}/api/tags",
                timeout=5,
            )
            response.raise_for_status()

            data = response.json()
            models = data.get("models", [])
            model_names = [m.get("name", "") for m in models]

            if self.model in model_names:
                self.is_available = True
                logger.info(f"Ollama disponível com modelo {self.model}")
            else:
                logger.warning(
                    f"Modelo {self.model} não encontrado no Ollama. "
                    f"Modelos disponíveis: {', '.join(model_names)}"
                )
                if model_names:
                    self.model = model_names[0]
                    self.model_name = f"ollama/{self.model}"
                    self.is_available = True
                    logger.info(f"Usando modelo alternativo: {self.model}")

        except requests.exceptions.RequestException as e:
            logger.warning(f"Ollama não disponível em {self.host}: {e}")
        except Exception as e:
            logger.warning(f"Erro ao verificar Ollama: {e}")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        if not self.is_available:
            raise RuntimeError(f"Ollama não está disponível em {self.host}")

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature or self.temperature,
                "top_p": self.top_p,
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

        effective_max_tokens = max_tokens or self.max_tokens
        payload["options"]["num_predict"] = effective_max_tokens

        structured_logger.log_llm_request(
            provider="ollama",
            model=self.model,
            prompt_length=len(prompt)
        )

        start_time = time.time()

        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()

            result = response.json()
            content = result.get("response", "")
            duration_ms = (time.time() - start_time) * 1000

            structured_logger.log_llm_response(
                provider="ollama",
                model=self.model,
                tokens=len(content.split()),
                duration_ms=duration_ms
            )

            return content

        except requests.exceptions.Timeout:
            structured_logger.log_llm_error(
                provider="ollama",
                model=self.model,
                error=f"Timeout ({self.timeout}s)"
            )
            raise
        except Exception as e:
            structured_logger.log_llm_error(
                provider="ollama",
                model=self.model,
                error=str(e)
            )
            raise

    def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Iterator[str]:
        """Stream tokens from Ollama API.

        Args:
            prompt: The input prompt for generation.
            system_prompt: Optional system prompt for context.
            temperature: Optional temperature override.
            max_tokens: Optional max tokens override.

        Yields:
            Generated tokens as strings.

        Raises:
            RuntimeError: If Ollama is not available.
        """
        if not self.is_available:
            raise RuntimeError(f"Ollama não está disponível em {self.host}")

        effective_max_tokens = max_tokens or self.max_tokens

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature or self.temperature,
                "top_p": self.top_p,
                "num_predict": effective_max_tokens,
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

        structured_logger.log_llm_request(
            provider="ollama",
            model=self.model,
            prompt_length=len(prompt)
        )

        start_time = time.time()
        token_count = 0

        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json=payload,
                timeout=self.timeout,
                stream=True,
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line)

                    if "response" in chunk:
                        token_count += 1
                        yield chunk["response"]

                    if chunk.get("done", False):
                        break

            duration_ms = (time.time() - start_time) * 1000
            structured_logger.log_llm_response(
                provider="ollama",
                model=self.model,
                tokens=token_count,
                duration_ms=duration_ms
            )

        except requests.exceptions.Timeout:
            structured_logger.log_llm_error(
                provider="ollama",
                model=self.model,
                error=f"Timeout ({self.timeout}s)"
            )
            raise
        except Exception as e:
            structured_logger.log_llm_error(
                provider="ollama",
                model=self.model,
                error=str(e)
            )
            raise
