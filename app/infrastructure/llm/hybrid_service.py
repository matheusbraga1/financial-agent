"""
Hybrid LLM Service - Groq with Ollama fallback.

Implements LLMPort with intelligent fallback mechanism.
Follows Open/Closed Principle (SOLID) - Easy to add new providers.
"""

import logging
from typing import Optional, Dict, Any, Iterable
from app.infrastructure.llm.groq_adapter import GroqAdapter
from app.infrastructure.llm.ollama_adapter import OllamaAdapter

logger = logging.getLogger(__name__)


class HybridLLMService:
    """
    Hybrid LLM service with automatic fallback.

    Strategy:
    1. Try Groq first (fast, cloud-based)
    2. If Groq fails, fallback to Ollama (slower, local)
    3. Log which provider was used for monitoring

    This implements the Liskov Substitution Principle (SOLID):
    - Can be used anywhere an LLMPort is expected
    - Transparent to the caller which provider is used
    """

    def __init__(
        self,
        groq_adapter: Optional[GroqAdapter] = None,
        ollama_adapter: Optional[OllamaAdapter] = None,
        prefer_groq: bool = True,
    ):
        """
        Initialize hybrid service.

        Args:
            groq_adapter: Groq adapter instance (optional)
            ollama_adapter: Ollama adapter instance (optional)
            prefer_groq: If True, try Groq first. Otherwise, try Ollama first.

        Raises:
            ValueError: If both adapters are None
        """
        if not groq_adapter and not ollama_adapter:
            raise ValueError("At least one LLM adapter must be provided")

        self.groq = groq_adapter
        self.ollama = ollama_adapter
        self.prefer_groq = prefer_groq

        # Determine primary and fallback
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
        """
        Generate completion with fallback.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            options: Additional options

        Returns:
            Generated text

        Raises:
            Exception: If both providers fail
        """
        # Try primary provider
        if self.primary:
            try:
                logger.info(f"Trying {self.primary_name}...")
                result = self.primary.generate(prompt, system_prompt, options)
                logger.info(f"✅ {self.primary_name} succeeded ({len(result)} chars)")
                return result
            except Exception as e:
                logger.warning(f"⚠️ {self.primary_name} failed: {e}")

        # Fallback to secondary provider
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
        """
        Stream completion with fallback.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            options: Additional options

        Yields:
            Text chunks

        Raises:
            Exception: If both providers fail
        """
        # Try primary provider
        if self.primary:
            try:
                logger.info(f"Streaming from {self.primary_name}...")
                for chunk in self.primary.stream(prompt, system_prompt, options):
                    yield chunk
                logger.info(f"✅ {self.primary_name} streaming succeeded")
                return  # Success, exit
            except Exception as e:
                logger.warning(f"⚠️ {self.primary_name} streaming failed: {e}")

        # Fallback to secondary provider
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
        """Get the name of the currently active (primary) provider."""
        return self.primary_name
