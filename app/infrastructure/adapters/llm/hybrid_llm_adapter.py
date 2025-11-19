from typing import Optional, Iterator
import logging

logger = logging.getLogger(__name__)

class HybridLLMAdapter:
    def __init__(
        self,
        groq_adapter: Optional[object] = None,
        ollama_adapter: Optional[object] = None,
        prefer_groq: bool = True,
    ):
        if not groq_adapter and not ollama_adapter:
            raise ValueError("Pelo menos um adapter deve ser fornecido")

        self.groq = groq_adapter
        self.ollama = ollama_adapter
        self.prefer_groq = prefer_groq

        if prefer_groq and groq_adapter:
            self.model_name = getattr(groq_adapter, "model_name", "groq/unknown")
        else:
            self.model_name = getattr(ollama_adapter, "model_name", "ollama/unknown")

        groq_available = groq_adapter is not None
        ollama_available = getattr(ollama_adapter, 'is_available', False) if ollama_adapter else False

        logger.info(
            f"HybridLLMAdapter inicializado: "
            f"groq={'✓' if groq_available else '✗'}, "
            f"ollama={'✓' if ollama_available else '✗'}, "
            f"prefer_groq={prefer_groq}"
        )

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        primary = self.groq if self.prefer_groq else self.ollama
        fallback = self.ollama if self.prefer_groq else self.groq

        if primary:
            try:
                logger.debug(f"Tentando provider primário: {primary.model_name}")

                result = primary.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                logger.info(f"Resposta gerada com {primary.model_name}")
                return result

            except Exception as e:
                logger.warning(
                    f"Falha no provider primário ({primary.model_name}): {e}"
                )

        if fallback:
            is_available = getattr(fallback, 'is_available', True)

            if not is_available:
                logger.error(f"Fallback {fallback.model_name} não está disponível")
                raise RuntimeError(
                    f"Nenhum provider LLM disponível. "
                    f"Primary: {getattr(primary, 'model_name', 'N/A')} falhou, "
                    f"Fallback: {fallback.model_name} não disponível"
                )

            try:
                logger.info(f"Usando fallback: {fallback.model_name}")

                result = fallback.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                logger.info(f"Resposta gerada com fallback {fallback.model_name}")
                return result

            except Exception as e:
                logger.error(f"Falha no fallback ({fallback.model_name}): {e}")
                raise

        raise RuntimeError("Nenhum provider LLM disponível")

    def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Iterator[str]:
        primary = self.groq if self.prefer_groq else self.ollama
        fallback = self.ollama if self.prefer_groq else self.groq

        if primary:
            try:
                logger.debug(f"Streaming com provider primário: {primary.model_name}")

                yield from primary.stream(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                )

                logger.info(f"Streaming concluído com {primary.model_name}")
                return

            except Exception as e:
                logger.warning(
                    f"Falha no streaming primário ({primary.model_name}): {e}"
                )

        if fallback:
            is_available = getattr(fallback, 'is_available', True)

            if not is_available:
                logger.error(f"Fallback {fallback.model_name} não está disponível")
                raise RuntimeError(
                    f"Nenhum provider LLM disponível para streaming. "
                    f"Primary: {getattr(primary, 'model_name', 'N/A')} falhou, "
                    f"Fallback: {fallback.model_name} não disponível"
                )

            try:
                logger.info(f"Streaming com fallback: {fallback.model_name}")

                yield from fallback.stream(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                )

                logger.info(f"Streaming concluído com fallback {fallback.model_name}")
                return

            except Exception as e:
                logger.error(f"Falha no streaming fallback ({fallback.model_name}): {e}")
                raise

        raise RuntimeError("Nenhum provider LLM disponível para streaming")
