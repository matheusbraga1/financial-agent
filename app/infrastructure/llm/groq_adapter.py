"""
Groq LLM Adapter - Fast cloud-based LLM provider.

Implements LLMPort using Groq API for ultra-fast inference.
Follows Single Responsibility Principle (SOLID).
"""

import logging
from typing import Optional, Dict, Any, Iterable
from groq import Groq

logger = logging.getLogger(__name__)


class GroqAdapter:
    """
    Adapter for Groq API (cloud-based LLM).

    Advantages:
    - Ultra-fast inference (50-100x faster than local CPU)
    - Free tier with generous limits (30 req/min)
    - Same models as Ollama (Llama 3.1, etc.)
    """

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.1-8b-instant",
        temperature: float = 0.2,
        top_p: float = 0.9,
        timeout: int = 30,
    ):
        """
        Initialize Groq adapter.

        Args:
            api_key: Groq API key
            model: Model name (e.g., "llama-3.1-8b-instant")
            temperature: Sampling temperature (0.0-1.0)
            top_p: Nucleus sampling parameter
            timeout: Request timeout in seconds
        """
        if not api_key:
            raise ValueError("Groq API key is required")

        self.client = Groq(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.timeout = timeout

        logger.info(f"GroqAdapter initialized with model={model}")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate completion using Groq API.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            options: Additional generation options (temperature, max_tokens, etc.)

        Returns:
            Generated text

        Raises:
            Exception: If Groq API call fails
        """
        try:
            # Prepare messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Merge options
            generation_options = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "max_tokens": 4096,  # Default max tokens
            }

            if options:
                generation_options.update(options)

            # Call Groq API
            logger.debug(f"Calling Groq API with model={self.model}")
            response = self.client.chat.completions.create(**generation_options)

            # Extract text
            text = response.choices[0].message.content
            logger.debug(f"Groq API returned {len(text)} chars")

            return text

        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise Exception(f"Groq generation failed: {str(e)}")

    def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterable[str]:
        """
        Stream completion tokens using Groq API.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            options: Additional generation options

        Yields:
            Text chunks as they are generated

        Raises:
            Exception: If Groq API call fails
        """
        try:
            # Prepare messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Merge options
            generation_options = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "max_tokens": 4096,
                "stream": True,  # Enable streaming
            }

            if options:
                generation_options.update(options)

            # Call Groq API with streaming
            logger.debug(f"Streaming from Groq API with model={self.model}")
            stream = self.client.chat.completions.create(**generation_options)

            # Yield tokens
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"Groq streaming error: {e}")
            raise Exception(f"Groq streaming failed: {str(e)}")
