#!/usr/bin/env python3
"""
Script para criar sessões e mensagens de teste para usuários existentes.

Útil para testar a funcionalidade de histórico e sessões.
"""

import sys
import os
import uuid
from datetime import datetime, timedelta

# Adicionar diretório ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.infrastructure.repositories.conversation_repository import SQLiteConversationRepository
from app.infrastructure.repositories.user_repository import SQLiteUserRepository

def main():
    print("=" * 80)
    print("CRIAR SESSÕES DE TESTE")
    print("=" * 80)

    # Repositórios
    user_repo = SQLiteUserRepository()
    conv_repo = SQLiteConversationRepository()

    # Buscar usuários
    import sqlite3
    conn = sqlite3.connect("app_data/users.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, username FROM users WHERE is_active = 1 LIMIT 5")
    users = [dict(row) for row in cur.fetchall()]
    conn.close()

    if not users:
        print("\n✗ Nenhum usuário encontrado!")
        return

    print(f"\n✓ Encontrados {len(users)} usuários:")
    for i, user in enumerate(users, 1):
        print(f"  {i}. {user['username']} (ID: {user['id']})")

    print("\n" + "=" * 80)
    response = input(f"Criar sessões de teste para esses usuários? (s/N): ").strip().lower()

    if response not in ['s', 'sim', 'y', 'yes']:
        print("\n✗ Operação cancelada.")
        return

    print("\n📝 Criando sessões de teste...")

    total_sessions = 0
    total_messages = 0

    for user in users:
        user_id = str(user['id'])
        username = user['username']

        # Criar 2-3 sessões por usuário
        num_sessions = 2

        for i in range(num_sessions):
            session_id = str(uuid.uuid4())

            # Criar sessão
            conv_repo.create_session(session_id, user_id)

            # Adicionar mensagens
            base_time = datetime.utcnow() - timedelta(days=i+1, hours=2)

            # Mensagem 1 - user
            conv_repo.add_message(
                session_id=session_id,
                role="user",
                content=f"Olá! Esta é uma pergunta de teste {i+1} do usuário {username}."
            )

            # Mensagem 2 - assistant
            conv_repo.add_message(
                session_id=session_id,
                role="assistant",
                answer=f"Olá! Esta é uma resposta de teste {i+1}. Como posso ajudar?",
                sources='[{"id": "test-doc-1", "title": "Documento de Teste", "score": 0.85}]',
                model="test-model",
                confidence=0.85
            )

            # Mensagem 3 - user
            conv_repo.add_message(
                session_id=session_id,
                role="user",
                content="Obrigado pelas informações!"
            )

            # Mensagem 4 - assistant
            conv_repo.add_message(
                session_id=session_id,
                role="assistant",
                answer="De nada! Estou sempre à disposição para ajudar.",
                sources='[]',
                model="test-model",
                confidence=0.90
            )

            total_sessions += 1
            total_messages += 4

        print(f"  ✓ {username}: {num_sessions} sessões criadas")

    print(f"\n✓ Criação concluída!")
    print(f"  - {total_sessions} sessões criadas")
    print(f"  - {total_messages} mensagens criadas")

    print("\n" + "=" * 80)
    print("TESTE: Verificando sessões criadas")
    print("=" * 80)

    # Verificar
    for user in users:
        user_id = str(user['id'])
        sessions = conv_repo.get_user_sessions(user_id=user_id, limit=10)

        print(f"\n{user['username']} (ID: {user_id}):")
        print(f"  - {len(sessions)} sessão(ões) encontrada(s)")

        for session in sessions:
            print(f"    • {session['session_id'][:8]}... - {session['message_count']} mensagens")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n✗ ERRO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
