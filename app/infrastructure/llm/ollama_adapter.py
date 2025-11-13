import logging
from typing import Optional, Dict, Any, Iterable
import ollama
from ollama import ResponseError

logger = logging.getLogger(__name__)

class OllamaAdapter:
    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "qwen2.5:3b",
        temperature: float = 0.2,
        top_p: float = 0.9,
        timeout: int = 120,
    ):
        self.host = host
        self.client = ollama.Client(host=host, timeout=timeout)
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.timeout = timeout

        logger.info(
            f"OllamaAdapter initialized with model={model} at {host} "
            f"(timeout={timeout}s)"
        )

    def _validate_model_available(self) -> None:
        try:
            models = self.client.list()
            model_names = [m['name'] for m in models.get('models', [])]
            
            if self.model not in model_names:
                logger.warning(
                    f"Model {self.model} not found in Ollama. "
                    f"Available models: {', '.join(model_names)}"
                )
                raise Exception(
                    f"Model '{self.model}' not found. "
                    f"Pull it with: ollama pull {self.model}"
                )
        except Exception as e:
            raise Exception(f"Ollama validation failed: {str(e)}")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            generation_options = {
                "temperature": self.temperature,
                "top_p": self.top_p,
            }

            if options:
                generation_options.update(options)

            logger.debug(
                f"Calling Ollama with model={self.model}, "
                f"temp={generation_options['temperature']}"
            )
            
            response = self.client.chat(
                model=self.model,
                messages=messages,
                options=generation_options,
                stream=False,
            )

            text = response["message"]["content"]
            
            if "eval_count" in response:
                logger.info(
                    f"Ollama success: {len(text)} chars, "
                    f"tokens: {response.get('eval_count', 'N/A')}"
                )
            else:
                logger.debug(f"Ollama returned {len(text)} chars")

            return text

        except ResponseError as e:
            logger.error(f"Ollama API error: {e}")
            raise Exception(f"Ollama generation failed: {str(e)}")
            
        except ConnectionError as e:
            logger.error(f"Cannot connect to Ollama at {self.host}: {e}")
            raise Exception(
                f"Ollama not reachable at {self.host}. "
                f"Is Ollama running? Start with: ollama serve"
            )
            
        except Exception as e:
            logger.error(f"Ollama unexpected error: {e}")
            raise Exception(f"Ollama generation failed: {str(e)}")

    def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterable[str]:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            generation_options = {
                "temperature": self.temperature,
                "top_p": self.top_p,
            }

            if options:
                generation_options.update(options)

            logger.debug(f"Streaming from Ollama with model={self.model}")
            
            stream = self.client.chat(
                model=self.model,
                messages=messages,
                options=generation_options,
                stream=True,
            )

            chunk_count = 0

            for chunk in stream:
                if "message" in chunk and "content" in chunk["message"]:
                    content = chunk["message"]["content"]
                    if content:
                        chunk_count += 1
                        yield content

            logger.info(f"Ollama streaming completed ({chunk_count} chunks)")

        except ResponseError as e:
            logger.error(f"Ollama streaming API error: {e}")
            raise Exception(f"Ollama streaming failed: {str(e)}")
            
        except ConnectionError as e:
            logger.error(f"Cannot connect to Ollama at {self.host}: {e}")
            raise Exception(
                f"Ollama not reachable at {self.host}. "
                f"Is Ollama running? Start with: ollama serve"
            )
            
        except Exception as e:
            logger.error(f"Ollama streaming unexpected error: {e}")
            raise Exception(f"Ollama streaming failed: {str(e)}")