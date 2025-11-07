import os
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.deps import get_user_service
from app.services.user_service import UserService


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Reduz custo de hash (PBKDF2) em testes
    monkeypatch.setenv("CI", "true")
    # Isola o banco de autenticação em um diretório temporário
    db_file = tmp_path / "auth_test.db"
    test_user_service = UserService(db_path=str(db_file))

    def _override_user_service():
        yield test_user_service

    app.dependency_overrides[get_user_service] = _override_user_service

    with TestClient(app) as c:
        yield c

    # limpa override
    app.dependency_overrides.pop(get_user_service, None)


def test_register_login_me_logout_flow(client):
    # registra usuário
    payload = {
        "email": "user@example.com",
        "password": "SuperSecret1",
        "name": "Usuário Teste",
    }
    r = client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == payload["email"].lower()
    assert body["is_active"] is True
    assert body["is_admin"] is False
    # created_at ISO
    datetime.fromisoformat(body["created_at"])  # não lança

    # tentar registrar de novo o mesmo email → 409
    r2 = client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 409

    # login com credenciais válidas
    r3 = client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert r3.status_code == 200, r3.text
    tok = r3.json()
    assert isinstance(tok["access_token"], str) and len(tok["access_token"]) > 10
    assert tok["expires_in"] > 0

    headers = {"Authorization": f"Bearer {tok['access_token']}"}

    # me com token válido
    r4 = client.get("/api/v1/auth/me", headers=headers)
    assert r4.status_code == 200, r4.text
    me = r4.json()
    assert me["email"] == payload["email"].lower()

    # logout revoga o token
    r5 = client.post("/api/v1/auth/logout", headers=headers)
    assert r5.status_code == 204, r5.text

    # token revogado não deve acessar /me
    r6 = client.get("/api/v1/auth/me", headers=headers)
    assert r6.status_code == 401


def test_login_invalid_credentials(client):
    # usuário inexistente
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "nouser@example.com", "password": "whatever123"},
    )
    assert r.status_code == 401

    # registra um usuário
    client.post(
        "/api/v1/auth/register",
        json={"email": "user2@example.com", "password": "Secret123", "name": "U2"},
    )

    # senha incorreta
    r2 = client.post(
        "/api/v1/auth/login",
        json={"email": "user2@example.com", "password": "wrongpass"},
    )
    assert r2.status_code == 401
