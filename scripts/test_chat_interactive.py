import logging
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.rag_service import rag_service

logging.basicConfig(
    level=logging.ERROR,
    format='%(message)s'
)

def chat_interactive():
    print("\n" + "=" * 70)
    print("🤖 CHAT INTERATIVO - TESTE COM DADOS REAIS")
    print("=" * 70)
    print("\nDigite suas perguntas (ou 'sair' para encerrar)")
    print("=" * 70)

    while True:
        print("\n")
        pergunta = input("❓ Você: ").strip()

        if not pergunta:
            continue

        if pergunta.lower() in ['sair', 'exit', 'quit', 'q']:
            print("\n👋 Até logo!")
            break

        try:
            print("\n🔍 Buscando informações...")
            response = rag_service.generate_answer(pergunta)

            print("\r" + " " * 50 + "\r", end='')

            if response.sources:
                print("\n📚 Fontes utilizadas:")
                for i, source in enumerate(response.sources, 1):
                    print(f"   {i}. [{source.category}] {source.title}")
                    print(f"      Relevância: {source.score:.1%}")
                print()

            print(f"\n🤖 Assistente:\n")
            print(response.answer)
            print("\n" + "-" * 70)

        except Exception as e:
            print(f"\n❌ Erro: {e}")


if __name__ == "__main__":
    try:
        chat_interactive()
    except KeyboardInterrupt:
        print("\n\n👋 Chat encerrado!")