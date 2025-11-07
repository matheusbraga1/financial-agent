import asyncio
import json
import pytest

from app.application.chat_usecase import ChatUseCase
from app.models.chat import ChatResponse


class FakeConversationService:
    def __init__(self):
        self.sessions = {}
        self.user_msgs = []
        self.assistant_msgs = []
        self.history_map = {}

    def ensure_session(self, session_id: str, user_id: str | None = None):
        self.sessions[session_id] = {"user_id": user_id}

    def add_user_message(self, session_id: str, content: str):
        self.user_msgs.append((session_id, content))

    def add_assistant_message(self, session_id: str, answer: str, sources_json: str | None, model_used: str | None, confidence: float | None):
        self.assistant_msgs.append((session_id, answer, sources_json, model_used, confidence))

    def get_history(self, session_id: str, limit: int = 100):
        return self.history_map.get(session_id, [])[-limit:]


class FakeRAG:
    def __init__(self):
        self.model = "fake-model"
        self.last_request = None

    async def generate_answer(self, question: str, top_k=None, min_score=None, history_rows=None) -> ChatResponse:
        self.last_request = {"q": question, "history": history_rows}
        return ChatResponse(answer="Resposta", sources=[], model_used=self.model, confidence=0.5)

    async def stream_answer(self, question: str, history_rows=None):
        # Emit sources, then tokens, then done
        yield ("sources", [{"id": "1", "title": "T", "category": "C", "score": 0.9, "snippet": "S"}])
        for t in ["He", "llo", " ", "world"]:
            yield ("token", t)
        yield ("_done", None)


@pytest.mark.asyncio
async def test_answer_unauthenticated_no_persist():
    rag = FakeRAG()
    conv = FakeConversationService()
    usecase = ChatUseCase(rag=rag, conversations=conv)

    resp = await usecase.answer("pergunta?", session_id=None, current_user=None)

    assert resp.persisted is False
    assert resp.session_id is None
    assert conv.user_msgs == []
    assert conv.assistant_msgs == []


@pytest.mark.asyncio
async def test_answer_authenticated_persist():
    rag = FakeRAG()
    conv = FakeConversationService()
    usecase = ChatUseCase(rag=rag, conversations=conv)

    user = {"id": 123}
    resp = await usecase.answer("pergunta?", session_id="sid-1", current_user=user)

    assert resp.persisted is True
    assert resp.session_id == "sid-1"
    assert conv.user_msgs == [("sid-1", "pergunta?")]
    # assistant persisted once
    assert len(conv.assistant_msgs) == 1
    _sid, answer, sources_json, model_used, conf = conv.assistant_msgs[0]
    assert _sid == "sid-1"
    assert answer == "Resposta"
    assert model_used == "fake-model"


@pytest.mark.asyncio
async def test_stream_authenticated_persist():
    rag = FakeRAG()
    conv = FakeConversationService()
    usecase = ChatUseCase(rag=rag, conversations=conv)

    user = {"id": 7}
    chunks = []
    async for s in usecase.stream_sse("Oi", session_id="s-2", current_user=user):
        assert s.startswith("data: ")
        data = json.loads(s[len("data: "):].strip())
        chunks.append(data.get("type"))

    # sources, many token, metadata, done
    assert "metadata" in chunks
    assert chunks[-1] == "done"

    # persisted assembled message
    assert len(conv.assistant_msgs) == 1
    _sid, answer, sources_json, model_used, conf = conv.assistant_msgs[0]
    assert _sid == "s-2"
    assert answer == "Hello world"
    assert model_used == "fake-model"

