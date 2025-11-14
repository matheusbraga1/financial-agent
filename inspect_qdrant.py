"""
Script para inspecionar o conteúdo do Qdrant e visualizar documentos armazenados
"""

import sys
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import json

def inspect_qdrant():
    """Conecta no Qdrant e lista documentos armazenados"""

    print("=" * 80)
    print("INSPEÇÃO DO QDRANT - BASE DE CONHECIMENTO")
    print("=" * 80)
    print()

    # Conecta no Qdrant
    try:
        client = QdrantClient(host="localhost", port=6333)
        print("[OK] Conectado ao Qdrant em localhost:6333")
    except Exception as e:
        print(f"[ERRO] Não foi possível conectar ao Qdrant: {e}")
        return

    # Lista coleções
    try:
        collections = client.get_collections()
        print(f"\n[INFO] Coleções encontradas: {len(collections.collections)}")

        for collection in collections.collections:
            print(f"  - {collection.name}")

        # Usa a primeira coleção encontrada ou 'artigos_glpi'
        if collections.collections:
            collection_name = collections.collections[0].name
        else:
            collection_name = "documents"

    except Exception as e:
        print(f"[ERRO] Erro ao listar coleções: {e}")
        return

    # Verifica se a coleção 'documents' existe
    try:
        collection_info = client.get_collection(collection_name=collection_name)
        print(f"\n[INFO] Coleção '{collection_name}':")
        print(f"  - Vetores: {collection_info.vectors_count}")
        print(f"  - Pontos: {collection_info.points_count}")

        if collection_info.points_count == 0:
            print("\n[AVISO] Nenhum documento encontrado na coleção!")
            print("Execute o script de ingestão de documentos primeiro.")
            return

    except Exception as e:
        print(f"[ERRO] Erro ao acessar coleção '{collection_name}': {e}")
        return

    # Busca documentos (scroll para pegar todos)
    print(f"\n{'=' * 80}")
    print("DOCUMENTOS ARMAZENADOS")
    print(f"{'=' * 80}\n")

    try:
        offset = None
        all_points = []
        batch_size = 100

        while True:
            result = client.scroll(
                collection_name=collection_name,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )

            points, next_offset = result

            if not points:
                break

            all_points.extend(points)

            if next_offset is None:
                break

            offset = next_offset

        print(f"[INFO] Total de documentos recuperados: {len(all_points)}\n")

        # Agrupa por tipo de documento
        by_type = {}
        by_department = {}

        for i, point in enumerate(all_points, 1):
            payload = point.payload

            doc_type = payload.get("doc_type", "unknown")
            department = payload.get("department", "unknown")

            if doc_type not in by_type:
                by_type[doc_type] = []
            by_type[doc_type].append(payload)

            if department not in by_department:
                by_department[department] = []
            by_department[department].append(payload)

        # Estatísticas
        print(f"{'=' * 80}")
        print("ESTATÍSTICAS")
        print(f"{'=' * 80}\n")

        print("Por Tipo de Documento:")
        for doc_type, docs in sorted(by_type.items()):
            print(f"  - {doc_type}: {len(docs)} documentos")

        print("\nPor Departamento:")
        for dept, docs in sorted(by_department.items()):
            print(f"  - {dept}: {len(docs)} documentos")

        # Amostra de documentos
        print(f"\n{'=' * 80}")
        print("AMOSTRA DE DOCUMENTOS (primeiros 10)")
        print(f"{'=' * 80}\n")

        for i, point in enumerate(all_points[:10], 1):
            payload = point.payload

            print(f"--- Documento {i} ---")
            print(f"ID: {point.id}")
            print(f"Título: {payload.get('title', 'N/A')}")
            print(f"Tipo: {payload.get('doc_type', 'N/A')}")
            print(f"Departamento: {payload.get('department', 'N/A')}")
            print(f"Conteúdo (primeiros 200 chars): {payload.get('content', 'N/A')[:200]}...")

            tags = payload.get('tags', [])
            if tags:
                print(f"Tags: {', '.join(tags)}")

            print()

        # Salva documentos únicos para criar queries
        print(f"{'=' * 80}")
        print("SALVANDO DOCUMENTOS ÚNICOS PARA ANÁLISE")
        print(f"{'=' * 80}\n")

        # Pega documentos únicos (por título)
        unique_docs = {}
        for point in all_points:
            payload = point.payload
            title = payload.get('title', '')

            if title and title not in unique_docs:
                unique_docs[title] = {
                    'id': str(point.id),
                    'title': title,
                    'content': payload.get('content', ''),
                    'doc_type': payload.get('doc_type', ''),
                    'department': payload.get('department', ''),
                    'tags': payload.get('tags', []),
                }

        # Salva em JSON
        output_file = "qdrant_documents_sample.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(list(unique_docs.values()), f, ensure_ascii=False, indent=2)

        print(f"[OK] {len(unique_docs)} documentos únicos salvos em: {output_file}")

        # Análise para criar queries
        print(f"\n{'=' * 80}")
        print("SUGESTÕES DE QUERIES PARA TESTE")
        print(f"{'=' * 80}\n")

        print("Baseado nos documentos encontrados, você pode testar queries como:")
        print()

        # Sugere queries baseadas nos títulos
        sample_titles = list(unique_docs.values())[:10]
        for i, doc in enumerate(sample_titles, 1):
            title = doc['title']
            # Cria uma query baseada no título
            if "resetar" in title.lower() or "senha" in title.lower():
                print(f"{i}. Como resetar minha senha?")
            elif "imprimir" in title.lower() or "impressora" in title.lower():
                print(f"{i}. Problemas com impressora")
            elif "email" in title.lower():
                print(f"{i}. Como configurar email?")
            elif "vpn" in title.lower():
                print(f"{i}. Não consigo conectar na VPN")
            else:
                # Pega primeiras palavras do título como query
                words = title.split()[:5]
                query = ' '.join(words)
                print(f"{i}. {query}")

    except Exception as e:
        print(f"[ERRO] Erro ao buscar documentos: {e}")
        import traceback
        traceback.print_exc()
        return


if __name__ == "__main__":
    inspect_qdrant()
