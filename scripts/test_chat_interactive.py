#!/usr/bin/env python3
"""
Script interativo para testar o chat com streaming em tempo real.

Uso:
    python scripts/test_chat_interactive.py

    # Com URL customizada
    python scripts/test_chat_interactive.py --url http://localhost:8000

    # Com usuário específico
    python scripts/test_chat_interactive.py --user-id 123

Comandos especiais:
    /quit, /exit    - Sair do chat
    /clear          - Limpar histórico
    /help           - Mostrar ajuda
    /stats          - Mostrar estatísticas da última resposta
"""

import sys
import os
import json
import argparse
from typing import Optional, Dict, Any, List
from datetime import datetime

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import httpx
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
except ImportError:
    print("Instalando dependências necessárias...")
    os.system(f"{sys.executable} -m pip install httpx rich")
    import httpx
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box

# Fix Windows encoding issues
import io
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

console = Console()


class ChatTester:
    """Cliente interativo para testar o endpoint /chat/stream"""

    def __init__(self, base_url: str = "http://localhost:8000", user_id: Optional[int] = None):
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id or 1
        self.conversation_id: Optional[int] = None
        self.last_sources: List[Dict[str, Any]] = []
        self.last_confidence: float = 0.0
        self.session_start = datetime.now()
        self.total_questions = 0

    def print_header(self):
        """Exibe cabeçalho do chat"""
        console.clear()
        header = f"""
[bold cyan]╔════════════════════════════════════════════════════════════════╗[/]
[bold cyan]║[/]  [bold white]Financial Agent - Chat Interativo[/]                         [bold cyan]║[/]
[bold cyan]╚════════════════════════════════════════════════════════════════╝[/]

[dim]URL:[/] {self.base_url}
[dim]User ID:[/] {self.user_id}
[dim]Conversation ID:[/] {self.conversation_id or 'Nova conversa'}

[yellow]Comandos:[/] /quit (sair) | /clear (limpar) | /stats (estatísticas) | /help (ajuda)
[dim]────────────────────────────────────────────────────────────────[/]
"""
        console.print(header)

    def print_help(self):
        """Exibe ajuda"""
        help_table = Table(title="Comandos Disponíveis", box=box.ROUNDED)
        help_table.add_column("Comando", style="cyan", no_wrap=True)
        help_table.add_column("Descrição", style="white")

        help_table.add_row("/quit, /exit", "Sair do chat")
        help_table.add_row("/clear", "Limpar histórico de conversa")
        help_table.add_row("/stats", "Mostrar estatísticas da última resposta")
        help_table.add_row("/help", "Mostrar esta ajuda")

        console.print("\n")
        console.print(help_table)
        console.print("\n")

    def print_stats(self):
        """Exibe estatísticas da última resposta"""
        if not self.last_sources:
            console.print("[yellow]Nenhuma estatística disponível ainda.[/]\n")
            return

        # Tabela de fontes
        sources_table = Table(title="Fontes Consultadas", box=box.ROUNDED)
        sources_table.add_column("#", style="dim", width=3)
        sources_table.add_column("Título", style="cyan")
        sources_table.add_column("Categoria", style="magenta")
        sources_table.add_column("Score", style="green", justify="right")

        for i, source in enumerate(self.last_sources[:5], 1):
            score = source.get("score", 0.0)
            score_str = f"{score:.2%}" if score else "N/A"
            sources_table.add_row(
                str(i),
                source.get("title", "N/A")[:50],
                source.get("category", "N/A"),
                score_str
            )

        # Painel de confiança
        confidence_color = "red" if self.last_confidence < 0.5 else "yellow" if self.last_confidence < 0.7 else "green"
        confidence_panel = Panel(
            f"[{confidence_color} bold]{self.last_confidence:.1%}[/]",
            title="Confiança da Resposta",
            border_style=confidence_color
        )

        console.print("\n")
        console.print(confidence_panel)
        console.print(sources_table)
        console.print("\n")

    def stream_chat(self, question: str) -> Optional[str]:
        """
        Envia pergunta e processa stream de resposta.

        Args:
            question: Pergunta do usuário

        Returns:
            Resposta completa ou None em caso de erro
        """
        url = f"{self.base_url}/api/v1/chat/stream"

        payload = {
            "question": question
        }

        if self.conversation_id:
            payload["session_id"] = self.conversation_id

        full_answer = ""

        try:
            console.print(f"\n[bold blue]Você:[/] {question}\n")
            console.print("[bold green]Assistente:[/] ", end="")

            # Timeout configurável: 10s para conectar, 300s para ler
            timeout_config = httpx.Timeout(10.0, read=300.0)

            with httpx.Client(timeout=timeout_config) as client:
                with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()

                    # Buffer para acumular dados parciais
                    buffer = b""

                    # Processa o stream byte por byte (forma correta para httpx)
                    for chunk in response.iter_raw():
                        if not chunk:
                            continue

                        buffer += chunk

                        # Processa todas as linhas completas no buffer
                        while b"\n" in buffer:
                            line_bytes, buffer = buffer.split(b"\n", 1)

                            try:
                                line = line_bytes.decode("utf-8").strip()
                            except UnicodeDecodeError:
                                # Ignora linhas com encoding inválido
                                continue

                            if not line or not line.startswith("data: "):
                                continue

                            data_str = line[6:]  # Remove "data: " prefix

                            if data_str == "[DONE]":
                                break

                            try:
                                data = json.loads(data_str)
                                event_type = data.get("type")

                                # Processa diferentes tipos de eventos do backend
                                if event_type == "sources":
                                    self.last_sources = data.get("sources", [])

                                elif event_type == "confidence":
                                    self.last_confidence = data.get("score", 0.0)

                                elif event_type == "token":
                                    token = data.get("content", "")
                                    console.print(token, end="", flush=True)
                                    full_answer += token

                                elif event_type == "metadata":
                                    # Captura session_id do metadata
                                    if "session_id" in data:
                                        self.conversation_id = data["session_id"]

                                elif event_type == "error":
                                    error_msg = data.get("message", "Erro desconhecido")
                                    console.print(f"\n\n[bold red]Erro:[/] {error_msg}\n")
                                    return None

                                elif event_type == "done":
                                    # Stream finalizado
                                    break

                            except json.JSONDecodeError:
                                # Linha inválida, ignora silenciosamente
                                continue

                    console.print("\n")

                    # Exibe mini resumo de confiança
                    if self.last_confidence > 0:
                        confidence_emoji = "🟢" if self.last_confidence >= 0.7 else "🟡" if self.last_confidence >= 0.5 else "🔴"
                        console.print(
                            f"[dim]{confidence_emoji} Confiança: {self.last_confidence:.1%} | "
                            f"Fontes: {len(self.last_sources)}[/]\n"
                        )

                    self.total_questions += 1
                    return full_answer

        except httpx.ConnectError:
            console.print(f"\n[bold red]Erro:[/] Não foi possível conectar ao servidor em {self.base_url}\n")
            console.print("[yellow]Certifique-se de que o backend está rodando:[/]")
            console.print("  python -m uvicorn app.main:app --reload\n")
            return None

        except httpx.TimeoutException:
            console.print("\n[bold red]Erro:[/] Timeout ao aguardar resposta do servidor\n")
            return None

        except httpx.HTTPStatusError as e:
            console.print(f"\n[bold red]Erro HTTP {e.response.status_code}:[/] {e.response.text}\n")
            return None

        except httpx.StreamError as e:
            console.print(f"\n[bold red]Erro de streaming:[/] {str(e)}\n")
            console.print("[yellow]Dica:[/] Certifique-se de que o endpoint /api/chat/stream está funcionando.\n")
            return None

        except Exception as e:
            console.print(f"\n[bold red]Erro inesperado:[/] {str(e)}\n")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/]\n")
            return None

    def clear_conversation(self):
        """Limpa o histórico da conversa"""
        self.conversation_id = None
        self.last_sources = []
        self.last_confidence = 0.0
        console.print("[green]Histórico limpo! Nova conversa iniciada.[/]\n")

    def run(self):
        """Loop principal do chat interativo"""
        self.print_header()

        console.print("[bold green]Chat iniciado![/] Digite sua pergunta ou /help para ajuda.\n")

        while True:
            try:
                # Prompt para o usuário
                question = console.input("[bold cyan]> [/]").strip()

                if not question:
                    continue

                # Processa comandos especiais
                if question.lower() in ["/quit", "/exit"]:
                    console.print("\n[bold yellow]Encerrando chat...[/]")
                    console.print(f"[dim]Total de perguntas: {self.total_questions}[/]")
                    console.print(f"[dim]Duração da sessão: {datetime.now() - self.session_start}[/]\n")
                    break

                elif question.lower() == "/clear":
                    self.clear_conversation()
                    self.print_header()
                    continue

                elif question.lower() == "/help":
                    self.print_help()
                    continue

                elif question.lower() == "/stats":
                    self.print_stats()
                    continue

                # Envia pergunta e processa resposta
                answer = self.stream_chat(question)

                if answer is None:
                    console.print("[yellow]Tente novamente ou digite /quit para sair.[/]\n")

            except KeyboardInterrupt:
                console.print("\n\n[bold yellow]Chat interrompido pelo usuário.[/]\n")
                break

            except EOFError:
                console.print("\n\n[bold yellow]EOF detectado. Encerrando...[/]\n")
                break


def main():
    parser = argparse.ArgumentParser(
        description="Chat interativo com streaming para testar o Financial Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  # Conectar ao servidor local padrão
  python scripts/test_chat_interactive.py

  # Conectar a um servidor customizado
  python scripts/test_chat_interactive.py --url http://192.168.1.100:8000

  # Usar um user_id específico
  python scripts/test_chat_interactive.py --user-id 42

Comandos durante o chat:
  /quit, /exit  - Sair
  /clear        - Limpar histórico
  /stats        - Ver estatísticas
  /help         - Ajuda
        """
    )

    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="URL base do servidor (padrão: http://localhost:8000)"
    )

    parser.add_argument(
        "--user-id",
        type=int,
        default=1,
        help="ID do usuário (padrão: 1)"
    )

    args = parser.parse_args()

    try:
        tester = ChatTester(base_url=args.url, user_id=args.user_id)
        tester.run()

    except Exception as e:
        console.print(f"\n[bold red]Erro fatal:[/] {str(e)}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
