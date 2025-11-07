import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.vector_store_service import vector_store_service
from app.services.glpi_service import GLPIService

print("\n" + "=" * 70)
print("ESTATÍSTICAS DO SISTEMA")
print("=" * 70)

print("\nGLPI (MySQL):")
glpi = GLPIService()
glpi_stats = glpi.get_stats()
print(f"   Total de artigos: {glpi_stats.get('total_articles', 0)}")
print(f"   Artigos públicos: {glpi_stats.get('public_articles', 0)}")
print(f"   Artigos FAQ: {glpi_stats.get('faq_articles', 0)}")
print(f"   Categorias: {glpi_stats.get('total_categories', 0)}")

print("\nQDRANT (Vector DB):")
qdrant_info = vector_store_service.get_collection_info()
print(f"   Collection: {qdrant_info['name']}")
print(f"   Documentos indexados: {qdrant_info['vectors_count']}")
print(f"   Dimensões dos vetores: {qdrant_info['vector_size']}")

sync_percentage = (qdrant_info['vectors_count'] / glpi_stats.get('public_articles', 1)) * 100
print(f"\nTaxa de sincronização: {sync_percentage:.1f}%")

print("=" * 70)

