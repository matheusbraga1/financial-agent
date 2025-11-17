#!/usr/bin/env python3
"""
Script de diagnóstico para verificar encoding do GLPI → Qdrant

Este script verifica:
1. Encoding do MySQL (charset da conexão e das tabelas)
2. Exemplos de conteúdo do GLPI antes e depois da limpeza
3. Conteúdo armazenado no Qdrant

Uso:
    python scripts/diagnose_encoding.py
    python scripts/diagnose_encoding.py --article-id 123
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

import logging
import argparse
from typing import Dict, Any, List
import unicodedata

from app.infrastructure.adapters.external.glpi_client import GLPIClient
from app.infrastructure.adapters.vector_store.qdrant_adapter import QdrantAdapter
from app.infrastructure.config.settings import get_settings
from glpi_ingestion.content_cleaner import create_content_cleaner

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_encoding_info(text: str, label: str):
    """Exibe informações detalhadas sobre encoding de um texto."""
    print(f"\n{'=' * 80}")
    print(f"{label}")
    print(f"{'=' * 80}")

    if not text:
        print("❌ Texto vazio")
        return

    print(f"📏 Tamanho: {len(text)} caracteres")
    print(f"📝 Preview (primeiros 200 chars):")
    print(f"   {text[:200]}")
    print()

    # Detectar problemas de encoding
    problems = []

    if "???" in text or "�" in text:
        problems.append("⚠️  PROBLEMA: Caracteres corrompidos detectados (??? ou �)")

    if "\ufffd" in text:
        problems.append("⚠️  PROBLEMA: Unicode replacement character (U+FFFD) detectado")

    # Verificar se tem caracteres acentuados válidos
    has_accents = any(
        unicodedata.category(char) == 'Ll' and char not in 'abcdefghijklmnopqrstuvwxyz'
        for char in text.lower()
    )

    if has_accents:
        problems.append("✅ Caracteres acentuados válidos detectados")
    else:
        problems.append("⚠️  Sem caracteres acentuados (pode estar corrompido se esperado)")

    # Mostrar problemas
    if problems:
        print("🔍 Análise:")
        for problem in problems:
            print(f"   {problem}")
    print()

    # Mostrar amostra de caracteres especiais
    special_chars = [char for char in set(text) if ord(char) > 127]
    if special_chars:
        print("🔤 Caracteres especiais encontrados:")
        for char in sorted(special_chars)[:20]:  # Primeiros 20
            unicode_name = unicodedata.name(char, f"U+{ord(char):04X}")
            print(f"   '{char}' (U+{ord(char):04X}) - {unicode_name}")
    else:
        print("⚠️  Nenhum caractere especial (acentuação) encontrado")


def check_mysql_encoding():
    """Verifica o encoding do MySQL."""
    print("\n" + "=" * 80)
    print("VERIFICANDO MYSQL ENCODING")
    print("=" * 80)

    try:
        glpi = GLPIClient()

        # Verificar charset da conexão
        with glpi._get_connection() as conn:
            cursor = conn.cursor()

            # Charset da conexão
            cursor.execute("SELECT @@character_set_connection, @@collation_connection")
            result = cursor.fetchone()
            print(f"\n✅ Connection Charset: {result}")

            # Charset do database
            cursor.execute("SELECT @@character_set_database, @@collation_database")
            result = cursor.fetchone()
            print(f"✅ Database Charset: {result}")

            # Charset das tabelas principais
            cursor.execute("""
                SELECT TABLE_NAME, TABLE_COLLATION
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME IN ('glpi_knowbaseitems', 'glpi_knowbaseitemtranslations')
            """)
            tables = cursor.fetchall()

            print(f"\n📊 Charset das tabelas principais:")
            for table in tables:
                print(f"   {table['TABLE_NAME']}: {table['TABLE_COLLATION']}")

            # Verificar charset das colunas de conteúdo
            cursor.execute("""
                SELECT COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'glpi_knowbaseitems'
                AND COLUMN_NAME IN ('name', 'answer')
            """)
            columns = cursor.fetchall()

            print(f"\n📝 Charset das colunas de conteúdo:")
            for col in columns:
                print(f"   {col['COLUMN_NAME']}: {col['CHARACTER_SET_NAME']} / {col['COLLATION_NAME']}")

        return True

    except Exception as e:
        print(f"\n❌ Erro ao verificar MySQL: {e}")
        return False


def check_article_encoding(article_id: int = None):
    """Verifica encoding de um artigo específico."""
    print("\n" + "=" * 80)
    print("VERIFICANDO ENCODING DE ARTIGO")
    print("=" * 80)

    try:
        glpi = GLPIClient()
        cleaner = create_content_cleaner()

        # Se não especificou ID, pega o primeiro
        if article_id is None:
            with glpi._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM glpi_knowbaseitems LIMIT 1")
                result = cursor.fetchone()
                if result:
                    article_id = result['id']
                else:
                    print("❌ Nenhum artigo encontrado no banco")
                    return False

        # Buscar artigo
        with glpi._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, answer
                FROM glpi_knowbaseitems
                WHERE id = %s
            """, (article_id,))

            article = cursor.fetchone()

            if not article:
                print(f"❌ Artigo {article_id} não encontrado")
                return False

            print(f"\n📄 Artigo ID: {article['id']}")

            # Analisar título
            print_encoding_info(article['name'], "TÍTULO (RAW do MySQL)")

            # Analisar conteúdo RAW
            print_encoding_info(article['answer'], "CONTEÚDO (RAW do MySQL)")

            # Analisar conteúdo após limpeza
            cleaned_content = cleaner.clean(article['answer'], article['name'])
            print_encoding_info(cleaned_content, "CONTEÚDO (APÓS LIMPEZA)")

        return True

    except Exception as e:
        print(f"\n❌ Erro ao verificar artigo: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_qdrant_encoding(limit: int = 3):
    """Verifica encoding de documentos no Qdrant."""
    print("\n" + "=" * 80)
    print("VERIFICANDO ENCODING NO QDRANT")
    print("=" * 80)

    try:
        settings = get_settings()
        qdrant = QdrantAdapter(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            collection_name=settings.qdrant_collection,
            vector_size=settings.embedding_dimension,
        )

        # Buscar alguns pontos
        results, _ = qdrant.client.scroll(
            collection_name=settings.qdrant_collection,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        if not results:
            print("⚠️  Nenhum documento encontrado no Qdrant")
            return True

        for i, point in enumerate(results, 1):
            payload = point.payload
            print(f"\n{'─' * 80}")
            print(f"Documento {i}/{len(results)} - ID: {point.id}")
            print(f"{'─' * 80}")

            # Analisar título
            if 'title' in payload:
                print_encoding_info(payload['title'], "TÍTULO (no Qdrant)")

            # Analisar conteúdo
            if 'content' in payload:
                content = payload['content']
                print_encoding_info(content, "CONTEÚDO (no Qdrant)")

        return True

    except Exception as e:
        print(f"\n❌ Erro ao verificar Qdrant: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Diagnosticar problemas de encoding GLPI → Qdrant"
    )

    parser.add_argument(
        "--article-id",
        type=int,
        help="ID do artigo para verificar (padrão: primeiro artigo)"
    )

    parser.add_argument(
        "--skip-mysql",
        action="store_true",
        help="Pular verificação do MySQL"
    )

    parser.add_argument(
        "--skip-qdrant",
        action="store_true",
        help="Pular verificação do Qdrant"
    )

    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("🔍 DIAGNÓSTICO DE ENCODING - GLPI → QDRANT")
    print("=" * 80)

    success = True

    # 1. Verificar MySQL
    if not args.skip_mysql:
        if not check_mysql_encoding():
            success = False

    # 2. Verificar artigo
    if not args.skip_mysql:
        if not check_article_encoding(args.article_id):
            success = False

    # 3. Verificar Qdrant
    if not args.skip_qdrant:
        if not check_qdrant_encoding():
            success = False

    # Resumo final
    print("\n" + "=" * 80)
    print("📋 RESUMO DO DIAGNÓSTICO")
    print("=" * 80)

    if success:
        print("\n✅ Diagnóstico concluído com sucesso!")
        print("\n💡 Próximos passos:")
        print("   1. Verifique os resultados acima")
        print("   2. Se encontrou '???' ou '�', o problema está no encoding do MySQL")
        print("   3. Se o MySQL está correto mas Qdrant tem problemas, re-execute a ingestão")
        print("   4. Instale ftfy para melhor correção: pip install ftfy")
    else:
        print("\n❌ Diagnóstico encontrou erros")
        print("\n💡 Verifique os logs acima para mais detalhes")

    print()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
