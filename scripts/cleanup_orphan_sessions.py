#!/usr/bin/env python3
"""
Script para limpar sessões órfãs (user_ids que não existem na tabela users).

Este script:
1. Identifica sessões com user_ids que não existem mais na tabela users
2. Oferece opção de deletar essas sessões
3. Mantém a integridade referencial do banco
"""

import sqlite3
import sys

users_db = "app_data/users.db"
chat_db = "app_data/chat_history.db"

def main():
    print("=" * 80)
    print("LIMPEZA DE SESSÕES ÓRFÃS")
    print("=" * 80)

    # Conectar aos bancos
    conn_users = sqlite3.connect(users_db)
    conn_users.row_factory = sqlite3.Row
    cur_users = conn_users.cursor()

    conn_chat = sqlite3.connect(chat_db)
    conn_chat.row_factory = sqlite3.Row
    cur_chat = conn_chat.cursor()

    # Buscar user_ids válidos
    cur_users.execute("SELECT id FROM users")
    valid_user_ids = {row['id'] for row in cur_users.fetchall()}

    print(f"\n✓ Usuários válidos encontrados: {len(valid_user_ids)}")
    print(f"  IDs: {sorted(valid_user_ids)}")

    # Buscar sessões com user_ids
    cur_chat.execute("""
        SELECT DISTINCT user_id
        FROM conversations
        WHERE user_id IS NOT NULL AND user_id != ''
    """)

    session_user_ids = [row['user_id'] for row in cur_chat.fetchall()]

    # Identificar órfãs
    orphan_user_ids = []
    for uid in session_user_ids:
        try:
            uid_int = int(uid)
            if uid_int not in valid_user_ids:
                orphan_user_ids.append(uid)
        except:
            orphan_user_ids.append(uid)

    if not orphan_user_ids:
        print("\n✓ Nenhuma sessão órfã encontrada!")
        print("  Todos os user_ids das sessões são válidos.")
        conn_users.close()
        conn_chat.close()
        return

    # Mostrar sessões órfãs
    print(f"\n⚠️  Sessões órfãs encontradas: {len(orphan_user_ids)} user_ids")
    print()

    total_orphan_sessions = 0
    total_orphan_messages = 0

    for uid in orphan_user_ids:
        # Contar sessões
        cur_chat.execute("""
            SELECT COUNT(*) as count
            FROM conversations
            WHERE user_id = ?
        """, (uid,))
        session_count = cur_chat.fetchone()['count']

        # Contar mensagens
        cur_chat.execute("""
            SELECT COUNT(*) as count
            FROM messages
            WHERE session_id IN (
                SELECT session_id FROM conversations WHERE user_id = ?
            )
        """, (uid,))
        message_count = cur_chat.fetchone()['count']

        total_orphan_sessions += session_count
        total_orphan_messages += message_count

        print(f"  User ID: {uid}")
        print(f"    - {session_count} sessão(ões)")
        print(f"    - {message_count} mensagem(ns)")

    print(f"\n📊 Total:")
    print(f"  - {total_orphan_sessions} sessões órfãs")
    print(f"  - {total_orphan_messages} mensagens órfãs")

    # Perguntar se deseja deletar
    print("\n" + "=" * 80)
    response = input("Deseja deletar todas as sessões órfãs? (s/N): ").strip().lower()

    if response not in ['s', 'sim', 'y', 'yes']:
        print("\n✗ Operação cancelada.")
        conn_users.close()
        conn_chat.close()
        return

    # Deletar sessões órfãs
    print("\n🗑️  Deletando sessões órfãs...")

    deleted_sessions = 0
    deleted_messages = 0

    for uid in orphan_user_ids:
        # Contar antes de deletar
        cur_chat.execute("""
            SELECT COUNT(*) as count
            FROM conversations
            WHERE user_id = ?
        """, (uid,))
        session_count = cur_chat.fetchone()['count']

        cur_chat.execute("""
            SELECT COUNT(*) as count
            FROM messages
            WHERE session_id IN (
                SELECT session_id FROM conversations WHERE user_id = ?
            )
        """, (uid,))
        message_count = cur_chat.fetchone()['count']

        # Deletar (CASCADE cuidará das mensagens e feedback)
        cur_chat.execute("""
            DELETE FROM conversations
            WHERE user_id = ?
        """, (uid,))

        deleted_sessions += session_count
        deleted_messages += message_count

        print(f"  ✓ User ID {uid}: {session_count} sessões e {message_count} mensagens deletadas")

    conn_chat.commit()

    print(f"\n✓ Limpeza concluída!")
    print(f"  - {deleted_sessions} sessões deletadas")
    print(f"  - {deleted_messages} mensagens deletadas")

    # Verificar estado final
    cur_chat.execute("""
        SELECT COUNT(*) as count
        FROM conversations
        WHERE user_id IS NOT NULL AND user_id != ''
    """)
    remaining = cur_chat.fetchone()['count']

    print(f"\n📊 Estado final:")
    print(f"  - {remaining} sessão(ões) restante(s) com user_id válido")

    conn_users.close()
    conn_chat.close()

    print("\n" + "=" * 80)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Operação interrompida pelo usuário.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERRO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
