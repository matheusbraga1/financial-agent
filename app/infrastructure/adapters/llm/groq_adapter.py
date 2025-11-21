from typing import Optional, Iterator, Dict, Any
import logging
from groq import Groq

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
    ):
        if not api_key:
            raise ValueError("Groq API key é obrigatória")
        
        self.client = Groq(api_key=api_key, timeout=timeout)
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.model_name = f"groq/{model}"
        
        logger.info(f"GroqAdapter inicializado: modelo={model}")
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        messages = []
        
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        messages.append({
            "role": "user",
            "content": prompt
        })
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                top_p=self.top_p,
                max_tokens=max_tokens or self.max_tokens,
            )
            
            content = response.choices[0].message.content
            
            logger.debug(
                f"Groq resposta gerada: {len(content)} chars, "
                f"tokens={response.usage.total_tokens if response.usage else 'N/A'}"
            )
            
            return content
            
        except Exception as e:
            logger.error(f"Erro ao chamar Groq API: {e}")
            raise
    
    def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Iterator[str]:
        """Stream tokens from Groq API.

        Args:
            prompt: The input prompt for generation.
            system_prompt: Optional system prompt for context.
            temperature: Optional temperature override.
            max_tokens: Optional max tokens override.

        Yields:
            Generated tokens as strings.
        """
        messages = []

        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        messages.append({
            "role": "user",
            "content": prompt
        })

        effective_max_tokens = max_tokens or self.max_tokens

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                top_p=self.top_p,
                max_tokens=effective_max_tokens,
                stream=True,
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

            logger.debug("Groq streaming concluído")

        except Exception as e:
            logger.error(f"Erro no streaming Groq: {e}")
            raise