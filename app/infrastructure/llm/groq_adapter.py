import logging
import time
from typing import Optional, Dict, Any, Iterable
from groq import Groq
from groq import RateLimitError

logger = logging.getLogger(__name__)

class GroqAdapter:
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
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        generation_options = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }

        if options:
            generation_options.update(options)

        for attempt in range(self.max_retries):
            try:
                logger.debug(
                    f"Calling Groq API (attempt {attempt + 1}/{self.max_retries}) "
                    f"with model={self.model}, max_tokens={generation_options.get('max_tokens')}"
                )

                response = self.client.chat.completions.create(**generation_options)

                text = response.choices[0].message.content

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
                wait_time = 2 ** attempt
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
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        generation_options = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "stream": True,
        }

        if options:
            generation_options.update(options)

        for attempt in range(self.max_retries):
            try:
                logger.debug(
                    f"Streaming from Groq API (attempt {attempt + 1}/{self.max_retries}) "
                    f"with model={self.model}, max_tokens={generation_options.get('max_tokens')}"
                )

                stream = self.client.chat.completions.create(**generation_options)

                total_chunks = 0

                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        total_chunks += 1
                        yield chunk.choices[0].delta.content

                logger.info(f"Groq streaming completed successfully ({total_chunks} chunks)")
                return

            except RateLimitError as e:
                wait_time = 2 ** attempt
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
