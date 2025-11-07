import logging
import sys
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Setup basic logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('chat_interactive.log')
    ]
)
logger = logging.getLogger(__name__)

llm_provider = os.getenv('LLM_PROVIDER', 'ollama')
logger.info(f"Using LLM provider: {llm_provider}")

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.rag_service import rag_service

def format_sources(sources: list) -> str:
    if not sources:
        return ""
    
    output = "\nFontes utilizadas:\n"
    for i, source in enumerate(sources, 1):
        output += f"   {i}. [{source.category}] {source.title}\n"
        output += f"      Relevância: {source.score:.1%}\n"
    return output

async def chat_interactive():
    """
    Interactive chat function for testing the RAG service with real data.
    Allows users to ask questions and get responses with source citations.
    """
    print("\n" + "=" * 70)
    print("Financial Agent - Chat Interativo")
    print("=" * 70)
    print("\nDigite suas perguntas (ou 'sair' para encerrar)")
    print("=" * 70)

    while True:
        try:
            print("\n")
            question = input("Você: ").strip()

            if not question:
                continue

            if question.lower() in ['sair', 'exit', 'quit', 'q']:
                print("\nAté logo!")
                break

            print("\nProcessando sua pergunta...")
            
            # Generate response using RAG service (now with await)
            response = await rag_service.generate_answer(question)

            # Clear the "Processing" message
            print("\r" + " " * 50 + "\r", end='')

            # Print sources if available
            if response.sources:
                print(format_sources(response.sources))

            # Print the answer
            print(f"\nAssistente:\n")
            print(response.answer)
            print("\n" + "-" * 70)

        except KeyboardInterrupt:
            print("\n\nChat encerrado pelo usuário!")
            break
        except Exception as e:
            logger.error(f"Erro ao processar pergunta: {str(e)}", exc_info=True)
            print(f"\nOcorreu um erro ao processar sua pergunta. Por favor, tente novamente.")

if __name__ == "__main__":
    try:
        asyncio.run(chat_interactive())
    except Exception as e:
        logger.error(f"Erro fatal na execução do chat: {str(e)}", exc_info=True)
        print("\nErro fatal na execução do chat. Verifique os logs para mais detalhes.")
        sys.exit(1)