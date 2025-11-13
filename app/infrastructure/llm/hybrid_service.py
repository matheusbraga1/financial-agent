import logging
from typing import Optional, Dict, Any, Iterable, List
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

        self._build_provider_chain()
        
        logger.info(
            f"HybridLLMService initialized: "
            f"Chain={' -> '.join(p['name'] for p in self.provider_chain)}"
        )

    def _build_provider_chain(self) -> None:
        self.provider_chain: List[Dict[str, Any]] = []
        
        if self.prefer_groq:
            if self.groq:
                self.provider_chain.append({
                    "name": "Groq",
                    "adapter": self.groq,
                    "check": self._check_groq_available
                })
            if self.ollama:
                self.provider_chain.append({
                    "name": "Ollama", 
                    "adapter": self.ollama,
                    "check": self._check_ollama_available
                })
        else:
            if self.ollama:
                self.provider_chain.append({
                    "name": "Ollama",
                    "adapter": self.ollama, 
                    "check": self._check_ollama_available
                })
            if self.groq:
                self.provider_chain.append({
                    "name": "Groq",
                    "adapter": self.groq,
                    "check": self._check_groq_available
                })

    def _check_groq_available(self) -> bool:
        return self.groq is not None

    def _check_ollama_available(self) -> bool:
        if not self.ollama:
            return False
            
        try:
            self.ollama.client.list()
            return True
        except Exception as e:
            logger.debug(f"Ollama availability check failed: {e}")
            return False

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        errors = []
        
        for provider in self.provider_chain:
            name = provider["name"]
            adapter = provider["adapter"]
            check = provider["check"]
            
            if not check():
                logger.debug(f"⏭️  Skipping {name} (not available)")
                continue
            
            try:
                logger.info(f"🔄 Trying {name}...")
                result = adapter.generate(prompt, system_prompt, options)
                logger.info(f"✅ {name} succeeded ({len(result)} chars)")
                return result
                
            except Exception as e:
                error_msg = str(e)
                errors.append(f"{name}: {error_msg}")
                logger.warning(f"⚠️  {name} failed: {error_msg}")
                continue
        
        error_summary = " | ".join(errors)
        logger.error(f"❌ All providers failed: {error_summary}")
        raise Exception(f"All LLM providers failed. Errors: {error_summary}")

    def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterable[str]:
        errors = []
        
        for provider in self.provider_chain:
            name = provider["name"]
            adapter = provider["adapter"]
            check = provider["check"]
            
            if not check():
                logger.debug(f"⏭️  Skipping {name} (not available)")
                continue
            
            try:
                logger.info(f"🔄 Streaming from {name}...")
                
                stream_generator = adapter.stream(prompt, system_prompt, options)
                first_chunk = next(stream_generator, None)
                
                if first_chunk is None:
                    logger.warning(f"⚠️  {name} returned empty stream")
                    continue
                
                yield first_chunk
                
                chunk_count = 1
                for chunk in stream_generator:
                    chunk_count += 1
                    yield chunk
                
                logger.info(f"✅ {name} streaming succeeded ({chunk_count} chunks)")
                return
                
            except StopIteration:
                logger.warning(f"⚠️  {name} returned empty stream")
                continue
                
            except Exception as e:
                error_msg = str(e)
                errors.append(f"{name}: {error_msg}")
                logger.warning(f"⚠️  {name} streaming failed: {error_msg}")
                continue
        
        error_summary = " | ".join(errors)
        logger.error(f"❌ All streaming providers failed: {error_summary}")
        raise Exception(f"All LLM providers failed. Errors: {error_summary}")

    def get_active_provider(self) -> str:
        if self.provider_chain:
            return self.provider_chain[0]["name"]
        return "None"

    def get_available_providers(self) -> List[str]:
        return [
            p["name"] 
            for p in self.provider_chain 
            if p["check"]()
        ]