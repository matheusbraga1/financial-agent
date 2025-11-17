#!/usr/bin/env python3
"""
Script interativo para testar o Financial Agent no terminal.

Uso:
    python scripts/test_agent.py
    python scripts/test_agent.py --url http://localhost:8000
    python scripts/test_agent.py --no-stream  # Modo síncrono

Comandos especiais:
    /quit, /exit       - Sair do chat
    /clear             - Limpar histórico e iniciar nova conversa
    /history           - Ver histórico completo da conversa
    /stats             - Mostrar estatísticas da última resposta
    /sources           - Ver fontes detalhadas da última resposta
    /help              - Mostrar ajuda
    /mode              - Alternar entre streaming e síncrono
"""

import sys
import os
import json
import argparse
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import httpx
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.markdown import Markdown
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
    from rich.syntax import Syntax
    from rich.prompt import Confirm
except ImportError:
    print("📦 Instalando dependências necessárias...")
    os.system(f"{sys.executable} -m pip install httpx rich")
    import httpx
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.markdown import Markdown
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
    from rich.syntax import Syntax
    from rich.prompt import Confirm

# Fix Windows encoding issues
import io
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

console = Console()


class FinancialAgentTester:
    """Cliente interativo para testar o Financial Agent."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        use_streaming: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.use_streaming = use_streaming
        self.session_id: Optional[str] = None
        self.conversation_history: List[Dict[str, Any]] = []
        self.last_sources: List[Dict[str, Any]] = []
        self.last_confidence: float = 0.0
        self.last_model: str = ""
        self.session_start = datetime.now()
        self.total_questions = 0
        self.total_tokens = 0

    def print_header(self):
        """Exibe cabeçalho do chat"""
        console.clear()

        mode_text = "[green]Streaming ✓[/]" if self.use_streaming else "[yellow]Síncrono[/]"
        session_text = self.session_id[:8] if self.session_id else "Nova conversa"

        header = f"""
[bold cyan]╔════════════════════════════════════════════════════════════════╗[/]
[bold cyan]║[/]  [bold white]Financial Agent - Terminal Interativo[/]                   [bold cyan]║[/]
[bold cyan]╚════════════════════════════════════════════════════════════════╝[/]

[dim]URL:[/] {self.base_url}
[dim]Modo:[/] {mode_text}
[dim]Sessão:[/] {session_text}
[dim]Perguntas:[/] {self.total_questions}

[yellow]Comandos:[/] /help (ajuda) | /quit (sair) | /clear (limpar) | /stats (estatísticas)
[dim]────────────────────────────────────────────────────────────────[/]
"""
        console.print(header)

    def print_help(self):
        """Exibe ajuda"""
        help_table = Table(title="📚 Comandos Disponíveis", box=box.ROUNDED)
        help_table.add_column("Comando", style="cyan", no_wrap=True)
        help_table.add_column("Descrição", style="white")

        help_table.add_row("/quit, /exit", "Sair do chat")
        help_table.add_row("/clear", "Limpar histórico e iniciar nova conversa")
        help_table.add_row("/history", "Ver histórico completo da conversa")
        help_table.add_row("/stats", "Mostrar estatísticas da última resposta")
        help_table.add_row("/sources", "Ver fontes detalhadas da última resposta")
        help_table.add_row("/mode", "Alternar entre streaming e síncrono")
        help_table.add_row("/help", "Mostrar esta ajuda")

        console.print("\n")
        console.print(help_table)
        console.print("\n")

    def print_stats(self):
        """Exibe estatísticas da última resposta"""
        if not self.last_sources and not self.last_confidence:
            console.print("[yellow]⚠️  Nenhuma estatística disponível ainda.[/]\n")
            return

        # Tabela de estatísticas gerais
        stats_table = Table(title="📊 Estatísticas da Sessão", box=box.ROUNDED)
        stats_table.add_column("Métrica", style="cyan")
        stats_table.add_column("Valor", style="green", justify="right")

        duration = datetime.now() - self.session_start
        stats_table.add_row("Tempo de sessão", str(duration).split('.')[0])
        stats_table.add_row("Total de perguntas", str(self.total_questions))
        stats_table.add_row("Fontes consultadas", str(len(self.last_sources)))
        stats_table.add_row("Modelo usado", self.last_model or "N/A")

        # Painel de confiança
        confidence_color = (
            "red" if self.last_confidence < 0.5
            else "yellow" if self.last_confidence < 0.7
            else "green"
        )
        confidence_panel = Panel(
            f"[{confidence_color} bold]{self.last_confidence:.1%}[/]",
            title="🎯 Confiança da Última Resposta",
            border_style=confidence_color
        )

        console.print("\n")
        console.print(stats_table)
        console.print(confidence_panel)
        console.print("\n")

    def print_sources(self):
        """Exibe fontes detalhadas"""
        if not self.last_sources:
            console.print("[yellow]⚠️  Nenhuma fonte disponível.[/]\n")
            return

        sources_table = Table(
            title=f"📚 Fontes Consultadas ({len(self.last_sources)})",
            box=box.ROUNDED,
            show_lines=True
        )
        sources_table.add_column("#", style="dim", width=3)
        sources_table.add_column("Título", style="cyan")
        sources_table.add_column("Categoria", style="magenta")
        sources_table.add_column("Score", style="green", justify="right", width=8)

        for i, source in enumerate(self.last_sources[:10], 1):
            score = source.get("score", 0.0)
            score_str = f"{score:.1%}" if score else "N/A"
            title = source.get("title", "N/A")
            category = source.get("category", "Geral")

            # Truncar título se muito longo
            if len(title) > 50:
                title = title[:47] + "..."

            sources_table.add_row(
                str(i),
                title,
                category,
                score_str
            )

        console.print("\n")
        console.print(sources_table)

        # Mostrar preview da melhor fonte
        if self.last_sources:
            best_source = self.last_sources[0]
            content_preview = best_source.get("content", "")[:200]
            if content_preview:
                preview_panel = Panel(
                    content_preview + ("..." if len(best_source.get("content", "")) > 200 else ""),
                    title="📄 Preview da Melhor Fonte",
                    border_style="cyan"
                )
                console.print(preview_panel)

        console.print("\n")

    def print_history(self):
        """Exibe histórico da conversa"""
        if not self.conversation_history:
            console.print("[yellow]⚠️  Nenhum histórico disponível.[/]\n")
            return

        console.print("\n")
        console.print(Panel(
            f"[bold cyan]Histórico da Conversa[/]\n[dim]Total: {len(self.conversation_history)} mensagens[/]",
            box=box.DOUBLE
        ))
        console.print("\n")

        for i, msg in enumerate(self.conversation_history, 1):
            role = msg.get("role", "")

            if role == "user":
                console.print(f"[bold blue]👤 Você:[/] {msg.get('content', '')}\n")
            elif role == "assistant":
                answer = msg.get('answer', '')
                confidence = msg.get('confidence', 0.0)
                sources_count = len(msg.get('sources', []))

                confidence_emoji = "🟢" if confidence >= 0.7 else "🟡" if confidence >= 0.5 else "🔴"

                console.print(f"[bold green]🤖 Assistente:[/] {confidence_emoji}")
                console.print(Markdown(answer))
                console.print(f"[dim]Confiança: {confidence:.1%} | Fontes: {sources_count}[/]\n")

        console.print("\n")

    def toggle_mode(self):
        """Alterna entre streaming e síncrono"""
        self.use_streaming = not self.use_streaming
        mode = "Streaming" if self.use_streaming else "Síncrono"
        console.print(f"\n[green]✓[/] Modo alterado para: [bold]{mode}[/]\n")

    def clear_conversation(self):
        """Limpa o histórico da conversa"""
        self.session_id = None
        self.conversation_history = []
        self.last_sources = []
        self.last_confidence = 0.0
        self.last_model = ""
        console.print("\n[green]✓[/] Histórico limpo! Nova conversa iniciada.\n")

    def chat_sync(self, question: str) -> Optional[Dict[str, Any]]:
        """Envia pergunta no modo síncrono"""
        url = f"{self.base_url}/api/v1/chat"

        payload = {"question": question}
        if self.session_id:
            payload["session_id"] = self.session_id

        try:
            console.print(f"\n[bold blue]👤 Você:[/] {question}\n")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("[cyan]Processando sua pergunta...", total=None)

                timeout_config = httpx.Timeout(10.0, read=120.0)
                with httpx.Client(timeout=timeout_config) as client:
                    response = client.post(url, json=payload)
                    response.raise_for_status()

                progress.update(task, completed=True)

            data = response.json()

            # Atualizar estado
            if not self.session_id and data.get("session_id"):
                self.session_id = data["session_id"]

            self.last_sources = data.get("sources", [])
            self.last_confidence = data.get("confidence", 0.0)
            self.last_model = data.get("model_used", "")

            # Adicionar ao histórico
            self.conversation_history.append({
                "role": "user",
                "content": question
            })
            self.conversation_history.append({
                "role": "assistant",
                "answer": data.get("answer", ""),
                "sources": self.last_sources,
                "confidence": self.last_confidence,
            })

            # Exibir resposta
            console.print("[bold green]🤖 Assistente:[/]")
            console.print(Markdown(data.get("answer", "")))
            console.print()

            # Mini resumo
            confidence_emoji = "🟢" if self.last_confidence >= 0.7 else "🟡" if self.last_confidence >= 0.5 else "🔴"
            console.print(
                f"[dim]{confidence_emoji} Confiança: {self.last_confidence:.1%} | "
                f"Fontes: {len(self.last_sources)} | "
                f"Modelo: {self.last_model}[/]\n"
            )

            self.total_questions += 1
            return data

        except httpx.ConnectError:
            console.print(f"\n[bold red]❌ Erro:[/] Não foi possível conectar ao servidor em {self.base_url}\n")
            console.print("[yellow]💡 Certifique-se de que o backend está rodando:[/]")
            console.print("  python -m uvicorn app.main:app --reload\n")
            return None

        except httpx.TimeoutException:
            console.print("\n[bold red]❌ Erro:[/] Timeout ao aguardar resposta do servidor\n")
            return None

        except httpx.HTTPStatusError as e:
            error_detail = e.response.json().get("detail", str(e)) if e.response.text else str(e)
            console.print(f"\n[bold red]❌ Erro HTTP {e.response.status_code}:[/] {error_detail}\n")
            return None

        except Exception as e:
            console.print(f"\n[bold red]❌ Erro inesperado:[/] {str(e)}\n")
            return None

    def chat_stream(self, question: str) -> Optional[str]:
        """Envia pergunta no modo streaming"""
        url = f"{self.base_url}/api/v1/chat/stream"

        payload = {"question": question}
        if self.session_id:
            payload["session_id"] = self.session_id

        full_answer = ""

        try:
            console.print(f"\n[bold blue]👤 Você:[/] {question}\n")
            console.print("[bold green]🤖 Assistente:[/] ", end="")

            timeout_config = httpx.Timeout(10.0, read=300.0)

            with httpx.Client(timeout=timeout_config) as client:
                with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()

                    buffer = b""

                    for chunk in response.iter_raw():
                        if not chunk:
                            continue

                        buffer += chunk

                        while b"\n" in buffer:
                            line_bytes, buffer = buffer.split(b"\n", 1)

                            try:
                                line = line_bytes.decode("utf-8").strip()
                            except UnicodeDecodeError:
                                continue

                            if not line or not line.startswith("data: "):
                                continue

                            data_str = line[6:]

                            if data_str == "[DONE]":
                                break

                            try:
                                data = json.loads(data_str)
                                event_type = data.get("type")
                                event_data = data.get("data")

                                if event_type == "sources":
                                    self.last_sources = event_data or []

                                elif event_type == "confidence":
                                    self.last_confidence = event_data or 0.0

                                elif event_type == "token":
                                    token = event_data or ""
                                    console.print(token, end="", flush=True)
                                    full_answer += token
                                    self.total_tokens += 1

                                elif event_type == "metadata":
                                    if "session_id" in event_data:
                                        self.session_id = event_data["session_id"]
                                    if "model_used" in event_data:
                                        self.last_model = event_data.get("model_used", "")

                                elif event_type == "error":
                                    error_msg = event_data.get("message", "Erro desconhecido")
                                    console.print(f"\n\n[bold red]❌ Erro:[/] {error_msg}\n")
                                    return None

                                elif event_type == "done":
                                    break

                            except json.JSONDecodeError:
                                continue

            console.print("\n")

            # Mini resumo
            if self.last_confidence > 0:
                confidence_emoji = "🟢" if self.last_confidence >= 0.7 else "🟡" if self.last_confidence >= 0.5 else "🔴"
                console.print(
                    f"[dim]{confidence_emoji} Confiança: {self.last_confidence:.1%} | "
                    f"Fontes: {len(self.last_sources)}[/]\n"
                )

            # Adicionar ao histórico
            self.conversation_history.append({
                "role": "user",
                "content": question
            })
            self.conversation_history.append({
                "role": "assistant",
                "answer": full_answer,
                "sources": self.last_sources,
                "confidence": self.last_confidence,
            })

            self.total_questions += 1
            return full_answer

        except httpx.ConnectError:
            console.print(f"\n[bold red]❌ Erro:[/] Não foi possível conectar ao servidor em {self.base_url}\n")
            console.print("[yellow]💡 Certifique-se de que o backend está rodando:[/]")
            console.print("  python -m uvicorn app.main:app --reload\n")
            return None

        except httpx.TimeoutException:
            console.print("\n[bold red]❌ Erro:[/] Timeout ao aguardar resposta do servidor\n")
            return None

        except httpx.HTTPStatusError as e:
            error_detail = e.response.json().get("detail", str(e)) if e.response.text else str(e)
            console.print(f"\n[bold red]❌ Erro HTTP {e.response.status_code}:[/] {error_detail}\n")
            return None

        except httpx.StreamError as e:
            console.print(f"\n[bold red]❌ Erro de streaming:[/] {str(e)}\n")
            return None

        except Exception as e:
            console.print(f"\n[bold red]❌ Erro inesperado:[/] {str(e)}\n")
            return None

    def run(self):
        """Loop principal do chat interativo"""
        self.print_header()

        console.print("[bold green]✨ Chat iniciado![/] Digite sua pergunta ou /help para ajuda.\n")

        while True:
            try:
                # Prompt para o usuário
                question = console.input("[bold cyan]> [/]").strip()

                if not question:
                    continue

                # Processa comandos especiais
                if question.lower() in ["/quit", "/exit"]:
                    console.print("\n[bold yellow]👋 Encerrando chat...[/]")
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

                elif question.lower() == "/sources":
                    self.print_sources()
                    continue

                elif question.lower() == "/history":
                    self.print_history()
                    continue

                elif question.lower() == "/mode":
                    self.toggle_mode()
                    continue

                # Envia pergunta
                if self.use_streaming:
                    answer = self.chat_stream(question)
                else:
                    result = self.chat_sync(question)
                    answer = result.get("answer") if result else None

                if answer is None:
                    console.print("[yellow]⚠️  Tente novamente ou digite /quit para sair.[/]\n")

            except KeyboardInterrupt:
                console.print("\n\n[bold yellow]⚠️  Chat interrompido pelo usuário.[/]\n")
                if Confirm.ask("Deseja sair?", default=True):
                    break
                else:
                    console.print("\n[green]✓[/] Continuando...\n")
                    continue

            except EOFError:
                console.print("\n\n[bold yellow]👋 EOF detectado. Encerrando...[/]\n")
                break


def main():
    parser = argparse.ArgumentParser(
        description="Chat interativo para testar o Financial Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  # Conectar ao servidor local padrão (com streaming)
  python scripts/test_agent.py

  # Conectar a um servidor customizado
  python scripts/test_agent.py --url http://192.168.1.100:8000

  # Usar modo síncrono (sem streaming)
  python scripts/test_agent.py --no-stream

Comandos durante o chat:
  /quit, /exit  - Sair
  /clear        - Limpar histórico
  /history      - Ver histórico completo
  /stats        - Ver estatísticas
  /sources      - Ver fontes detalhadas
  /mode         - Alternar streaming/síncrono
  /help         - Ajuda
        """
    )

    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="URL base do servidor (padrão: http://localhost:8000)"
    )

    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Usar modo síncrono ao invés de streaming"
    )

    args = parser.parse_args()

    try:
        tester = FinancialAgentTester(
            base_url=args.url,
            use_streaming=not args.no_stream,
        )
        tester.run()

    except Exception as e:
        console.print(f"\n[bold red]❌ Erro fatal:[/] {str(e)}\n")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/]\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
