"""
Ollama LLM Adapter - Local LLM provider.

Implements LLMPort using Ollama for local inference.
Follows Single Responsibility Principle (SOLID).
"""

import logging
from typing import Optional, Dict, Any, Iterable
import ollama

logger = logging.getLogger(__name__)


class OllamaAdapter:
    """
    Adapter for Ollama (local LLM).

    Advantages:
    - Free and private (runs locally)
    - No API rate limits
    - Works offline

    Disadvantages:
    - Slower than cloud APIs (especially on CPU)
    - Requires local resources (RAM, GPU)
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "llama3.1:8b",
        temperature: float = 0.2,
        top_p: float = 0.9,
        timeout: int = 120,
    ):
        """
        Initialize Ollama adapter.

        Args:
            host: Ollama server URL
            model: Model name (e.g., "llama3.1:8b")
            temperature: Sampling temperature (0.0-1.0)
            top_p: Nucleus sampling parameter
            timeout: Request timeout in seconds
        """
        self.client = ollama.Client(host=host)
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.timeout = timeout

        logger.info(f"OllamaAdapter initialized with model={model} at {host}")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate completion using Ollama.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            options: Additional generation options

        Returns:
            Generated text

        Raises:
            Exception: If Ollama call fails
        """
        try:
            # Prepare messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Merge options
            generation_options = {
                "temperature": self.temperature,
                "top_p": self.top_p,
            }

            if options:
                generation_options.update(options)

            # Call Ollama
            logger.debug(f"Calling Ollama with model={self.model}")
            response = self.client.chat(
                model=self.model,
                messages=messages,
                options=generation_options,
                stream=False,
            )

            # Extract text
            text = response["message"]["content"]
            logger.debug(f"Ollama returned {len(text)} chars")

            return text

        except Exception as e:
            logger.error(f"Ollama error: {e}")
            raise Exception(f"Ollama generation failed: {str(e)}")

    def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterable[str]:
        """
        Stream completion tokens using Ollama.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            options: Additional generation options

        Yields:
            Text chunks as they are generated

        Raises:
            Exception: If Ollama call fails
        """
        try:
            # Prepare messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Merge options
            generation_options = {
                "temperature": self.temperature,
                "top_p": self.top_p,
            }

            if options:
                generation_options.update(options)

            # Call Ollama with streaming
            logger.debug(f"Streaming from Ollama with model={self.model}")
            stream = self.client.chat(
                model=self.model,
                messages=messages,
                options=generation_options,
                stream=True,
            )

            # Yield tokens
            for chunk in stream:
                if "message" in chunk and "content" in chunk["message"]:
                    yield chunk["message"]["content"]

        except Exception as e:
            logger.error(f"Ollama streaming error: {e}")
            raise Exception(f"Ollama streaming failed: {str(e)}")
