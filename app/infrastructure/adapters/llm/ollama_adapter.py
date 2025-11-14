from typing import Optional, Iterator
import logging
import requests

logger = logging.getLogger(__name__)

class OllamaAdapter:
    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "llama3.1:8b",
        temperature: float = 0.2,
        top_p: float = 0.9,
        timeout: int = 120,
    ):
        self.host = host.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.timeout = timeout
        self.model_name = f"ollama/{model}"
        self.is_available = False

        # Health check durante inicialização
        self._check_availability()

        logger.info(
            f"OllamaAdapter inicializado: host={host}, modelo={model}, "
            f"disponível={'✓' if self.is_available else '✗'}"
        )

    def _check_availability(self) -> None:
        """Verifica se o Ollama está disponível e se o modelo existe"""
        try:
            # Testa conexão com Ollama
            response = requests.get(
                f"{self.host}/api/tags",
                timeout=5,
            )
            response.raise_for_status()

            # Verifica se o modelo existe
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
                # Se o modelo não existe, tenta usar o primeiro disponível
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
        """Gera resposta usando Ollama"""
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

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()

            result = response.json()
            content = result.get("response", "")

            logger.debug(f"Ollama resposta gerada: {len(content)} chars")

            return content

        except requests.exceptions.Timeout:
            logger.error(f"Timeout ao chamar Ollama ({self.timeout}s)")
            raise
        except Exception as e:
            logger.error(f"Erro ao chamar Ollama: {e}")
            raise

    def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Iterator[str]:
        """Streaming de resposta usando Ollama"""
        if not self.is_available:
            raise RuntimeError(f"Ollama não está disponível em {self.host}")

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature or self.temperature,
                "top_p": self.top_p,
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

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
                    import json
                    chunk = json.loads(line)

                    if "response" in chunk:
                        yield chunk["response"]

                    if chunk.get("done", False):
                        break

            logger.debug("Ollama streaming concluído")

        except Exception as e:
            logger.error(f"Erro no streaming Ollama: {e}")
            raise
