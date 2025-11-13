"""
Groq LLM Adapter - Fast cloud-based LLM provider.

Implements LLMPort using Groq API for ultra-fast inference.
Follows Single Responsibility Principle (SOLID).
"""

import logging
import time
from typing import Optional, Dict, Any, Iterable
from groq import Groq
from groq import RateLimitError

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
        max_tokens: int = 2048,
        max_retries: int = 3,
    ):
        """
        Initialize Groq adapter.

        Args:
            api_key: Groq API key
            model: Model name (e.g., "llama-3.1-8b-instant")
            temperature: Sampling temperature (0.0-1.0)
            top_p: Nucleus sampling parameter
            timeout: Request timeout in seconds
            max_tokens: Maximum tokens in response (default: 2048, free tier limit: 6000 TPM)
            max_retries: Maximum retry attempts for rate limit errors (default: 3)
        """
        if not api_key:
            raise ValueError("Groq API key is required")

        self.client = Groq(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.max_retries = max_retries

        logger.info(
            f"GroqAdapter initialized with model={model}, max_tokens={max_tokens}, "
            f"max_retries={max_retries}"
        )

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate completion using Groq API with automatic retry on rate limits.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            options: Additional generation options (temperature, max_tokens, etc.)

        Returns:
            Generated text

        Raises:
            Exception: If Groq API call fails after all retries
        """
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
            "max_tokens": self.max_tokens,
        }

        if options:
            generation_options.update(options)

        # Retry logic with exponential backoff
        for attempt in range(self.max_retries):
            try:
                logger.debug(
                    f"Calling Groq API (attempt {attempt + 1}/{self.max_retries}) "
                    f"with model={self.model}, max_tokens={generation_options.get('max_tokens')}"
                )

                response = self.client.chat.completions.create(**generation_options)

                # Extract text
                text = response.choices[0].message.content

                # Log token usage if available
                if hasattr(response, 'usage') and response.usage:
                    logger.info(
                        f"Groq API success: {len(text)} chars, "
                        f"tokens: {response.usage.total_tokens} "
                        f"(prompt: {response.usage.prompt_tokens}, "
                        f"completion: {response.usage.completion_tokens})"
                    )
                else:
                    logger.debug(f"Groq API returned {len(text)} chars")

                return text

            except RateLimitError as e:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                logger.warning(
                    f"Rate limit hit (attempt {attempt + 1}/{self.max_retries}): {e}. "
                    f"Waiting {wait_time}s before retry..."
                )

                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    logger.error("Max retries reached for rate limit error")
                    raise Exception(
                        f"Groq rate limit exceeded after {self.max_retries} attempts. "
                        f"Consider reducing max_tokens or request frequency."
                    )

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
        Stream completion tokens using Groq API with automatic retry on rate limits.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            options: Additional generation options

        Yields:
            Text chunks as they are generated

        Raises:
            Exception: If Groq API call fails after all retries
        """
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
            "max_tokens": self.max_tokens,
            "stream": True,  # Enable streaming
        }

        if options:
            generation_options.update(options)

        # Retry logic with exponential backoff
        for attempt in range(self.max_retries):
            try:
                logger.debug(
                    f"Streaming from Groq API (attempt {attempt + 1}/{self.max_retries}) "
                    f"with model={self.model}, max_tokens={generation_options.get('max_tokens')}"
                )

                stream = self.client.chat.completions.create(**generation_options)

                # Track tokens for logging
                total_chunks = 0

                # Yield tokens
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        total_chunks += 1
                        yield chunk.choices[0].delta.content

                logger.info(f"Groq streaming completed successfully ({total_chunks} chunks)")
                return  # Success, exit retry loop

            except RateLimitError as e:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                logger.warning(
                    f"Rate limit hit during streaming (attempt {attempt + 1}/{self.max_retries}): {e}. "
                    f"Waiting {wait_time}s before retry..."
                )

                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    logger.error("Max retries reached for rate limit error in streaming")
                    raise Exception(
                        f"Groq rate limit exceeded after {self.max_retries} attempts. "
                        f"Consider reducing max_tokens or request frequency."
                    )

            except Exception as e:
                logger.error(f"Groq streaming error: {e}")
                raise Exception(f"Groq streaming failed: {str(e)}")
