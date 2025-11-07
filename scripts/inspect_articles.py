import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.vector_store_service import vector_store_service
from app.services.embedding_service import embedding_service


def search_and_inspect(query: str):
    """Busca e mostra conteúdo completo."""

    print("\n" + "=" * 70)
    print(f"BUSCANDO: {query}")
    print("=" * 70)

    vector = embedding_service.encode_text(query)

    results = vector_store_service.search_similar(
        query_vector=vector,
        limit=3,
    )

    if not results:
        print("\nNenhum resultado encontrado")
        return

    for i, doc in enumerate(results, 1):
        print(f"\n{'=' * 70}")
        print(f"RESULTADO {i}")
        print(f"{'=' * 70}")
        print(f"Título: {doc['title']}")
        print(f"Categoria: {doc['category']}")
        print(f"Score: {doc['score']:.1%}")
        print(f"Tamanho do conteúdo: {len(doc['content'])} caracteres")
        print(f"\n--- CONTEÚDO COMPLETO ---")
        print(doc['content'])
        print(f"--- FIM DO CONTEÚDO ---\n")


if __name__ == "__main__":
    query = "como faço para resolver o erro de execução da financial sistemas"
    search_and_inspect(query)

