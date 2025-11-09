import logging
from typing import Optional, Dict, Any, Iterable
from app.infrastructure.llm.groq_adapter import GroqAdapter
from app.infrastructure.llm.ollama_adapter import OllamaAdapter

logger = logging.getLogger(__name__)

class HybridLLMService:
    def __init__(
        self,
        groq_adapter: Optional[GroqAdapter] = None,
        ollama_adapter: Optional[OllamaAdapter] = None,
        prefer_groq: bool = True,
    ):
        if not groq_adapter and not ollama_adapter:
            raise ValueError("At least one LLM adapter must be provided")

        self.groq = groq_adapter
        self.ollama = ollama_adapter
        self.prefer_groq = prefer_groq

        if prefer_groq and groq_adapter:
            self.primary = groq_adapter
            self.primary_name = "Groq"
            self.fallback = ollama_adapter
            self.fallback_name = "Ollama"
        else:
            self.primary = ollama_adapter
            self.primary_name = "Ollama"
            self.fallback = groq_adapter
            self.fallback_name = "Groq"

        logger.info(
            f"HybridLLMService initialized: Primary={self.primary_name}, "
            f"Fallback={self.fallback_name if self.fallback else 'None'}"
        )

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        if self.primary:
            try:
                logger.info(f"Trying {self.primary_name}...")
                result = self.primary.generate(prompt, system_prompt, options)
                logger.info(f"✅ {self.primary_name} succeeded ({len(result)} chars)")
                return result
            except Exception as e:
                logger.warning(f"⚠️ {self.primary_name} failed: {e}")

        if self.fallback:
            try:
                logger.info(f"Falling back to {self.fallback_name}...")
                result = self.fallback.generate(prompt, system_prompt, options)
                logger.info(f"✅ {self.fallback_name} succeeded ({len(result)} chars)")
                return result
            except Exception as e:
                logger.error(f"❌ {self.fallback_name} also failed: {e}")
                raise Exception(f"All LLM providers failed. Last error: {str(e)}")

        raise Exception("No LLM providers available")

    def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterable[str]:
        if self.primary:
            try:
                logger.info(f"Streaming from {self.primary_name}...")
                for chunk in self.primary.stream(prompt, system_prompt, options):
                    yield chunk
                logger.info(f"✅ {self.primary_name} streaming succeeded")
                return  # Success, exit
            except Exception as e:
                logger.warning(f"⚠️ {self.primary_name} streaming failed: {e}")

        if self.fallback:
            try:
                logger.info(f"Falling back to {self.fallback_name} streaming...")
                for chunk in self.fallback.stream(prompt, system_prompt, options):
                    yield chunk
                logger.info(f"✅ {self.fallback_name} streaming succeeded")
                return  # Success, exit
            except Exception as e:
                logger.error(f"❌ {self.fallback_name} streaming also failed: {e}")
                raise Exception(f"All LLM providers failed. Last error: {str(e)}")

        raise Exception("No LLM providers available")

    def get_active_provider(self) -> str:
        return self.primary_name
