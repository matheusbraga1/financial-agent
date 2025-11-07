"""
LLM Adapters and Hybrid Service.

Provides implementations of LLMPort for different providers:
- GroqAdapter: Fast cloud-based LLM (Groq API)
- OllamaAdapter: Local LLM (Ollama)
- HybridLLMService: Intelligent fallback between providers
"""

from app.infrastructure.llm.groq_adapter import GroqAdapter
from app.infrastructure.llm.ollama_adapter import OllamaAdapter
from app.infrastructure.llm.hybrid_service import HybridLLMService

__all__ = ["GroqAdapter", "OllamaAdapter", "HybridLLMService"]
