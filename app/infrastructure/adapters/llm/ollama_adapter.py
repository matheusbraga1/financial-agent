from typing import Optional, Iterator
import logging
import requests

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
        self.host = host.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.timeout = timeout
        self.model_name = f"ollama/{model}"
        
        logger.info(f"OllamaAdapter inicializado: host={host}, modelo={model}")
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
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