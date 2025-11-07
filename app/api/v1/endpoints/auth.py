from fastapi import APIRouter, Depends, HTTPException, status, Request
from datetime import datetime

from app.models.auth import RegisterRequest, LoginRequest, TokenResponse, UserPublic
from app.models.error import ErrorResponse
from app.api.deps import get_user_service
from app.services.user_service import UserService
from app.utils.security import hash_password, verify_password, create_access_token
from app.api.security import get_current_user


router = APIRouter()


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar novo usuário",
    description="""
    Cria uma nova conta de usuário no sistema.

    **Requisitos:**
    - Email válido (único no sistema)
    - Senha com no mínimo 8 caracteres (recomendado: letras, números e símbolos)
    - Nome completo do usuário (opcional)

    **Importante:**
    - Usuários comuns não têm permissão de administrador por padrão
    - A senha será criptografada usando PBKDF2 com 200.000 iterações
    - Após criar a conta, use o endpoint `/login` para obter um token JWT

    **Exemplo de uso:**
    ```bash
    curl -X POST "http://localhost:8000/api/v1/auth/register" \\
         -H "Content-Type: application/json" \\
         -d '{
           "email": "joao.silva@empresa.com.br",
           "password": "Senha@123",
           "name": "João Silva"
         }'
    ```
    """,
    responses={
        201: {
            "description": "Usuário criado com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "id": 1,
                        "email": "joao.silva@empresa.com.br",
                        "name": "João Silva",
                        "is_active": True,
                        "is_admin": False,
                        "created_at": "2025-11-07T14:30:00"
                    }
                }
            }
        },
        400: {"description": "Dados inválidos (senha muito curta, email inválido, etc.)", "model": ErrorResponse},
        409: {"description": "E-mail já cadastrado no sistema", "model": ErrorResponse},
        500: {"description": "Erro interno do servidor", "model": ErrorResponse},
    },
)
async def register(req: RegisterRequest, user_service: UserService = Depends(get_user_service)) -> UserPublic:
    import asyncio

    loop = asyncio.get_running_loop()

    # Verifica se email já existe (operação síncrona em thread pool)
    existing = await loop.run_in_executor(
        None, user_service.get_user_by_email, req.email
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado")

    # Hash de senha em thread pool (operação CPU-bound)
    pwd_hash = await loop.run_in_executor(
        None, hash_password, req.password
    )

    # Cria usuário em thread pool
    user = await loop.run_in_executor(
        None, user_service.create_user, req.email, pwd_hash, req.name
    )

    return UserPublic(
        id=user["id"],
        email=user["email"],
        name=user.get("name"),
        is_active=bool(user.get("is_active")),
        is_admin=bool(user.get("is_admin")),
        created_at=datetime.fromisoformat(user["created_at"]),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Autenticar usuário",
    description="""
    Realiza login no sistema e retorna um token JWT para autenticação.

    **Como usar o token:**
    1. Copie o `access_token` da resposta
    2. Clique no botão **🔓 Authorize** no topo da página
    3. Cole o token (somente o token, sem "Bearer")
    4. Clique em "Authorize" e depois "Close"
    5. Agora você pode testar endpoints protegidos!

    **Exemplos de uso:**
    ```bash
    # Requisição HTTP
    curl -X POST "http://localhost:8000/api/v1/auth/login" \\
         -H "Content-Type: application/json" \\
         -d '{"email": "joao.silva@empresa.com.br", "password": "Senha@123"}'

    # Usando o token
    curl -X GET "http://localhost:8000/api/v1/auth/me" \\
         -H "Authorization: Bearer eyJhbGciOiJIUz..."
    ```
    """,
    responses={
        200: {
            "description": "Login realizado com sucesso - Token JWT gerado",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiaXNzIjoiQ2hhdCBJQSBHTFBJIiwiaWF0IjoxNjk5OTk5OTk5LCJleHAiOjE3MDAwMDM1OTl9.xxxxx",
                        "token_type": "bearer",
                        "expires_in": 3600
                    }
                }
            }
        },
        400: {"description": "Dados inválidos (email malformado, senha vazia, etc.)", "model": ErrorResponse},
        401: {"description": "Email ou senha incorretos", "model": ErrorResponse},
        500: {"description": "Erro interno do servidor", "model": ErrorResponse},
    },
)
async def login(req: LoginRequest, user_service: UserService = Depends(get_user_service)) -> TokenResponse:
    import asyncio

    loop = asyncio.get_running_loop()

    # Busca usuário em thread pool
    user = await loop.run_in_executor(
        None, user_service.get_user_by_email, req.email
    )

    # Verifica senha em thread pool (PBKDF2 é CPU-bound)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")

    password_valid = await loop.run_in_executor(
        None, verify_password, req.password, user["password_hash"]
    )

    if not password_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")

    extra = {
        "email": user["email"],
        "name": user.get("name"),
        "is_admin": bool(user.get("is_admin")),
    }
    tok = create_access_token(subject=str(user["id"]), claims=extra)
    return TokenResponse(
        access_token=tok["token"],
        expires_in=int((tok["exp"] - datetime.now(tok["exp"].tzinfo)).total_seconds()),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desconectar usuário",
    description="""
    Revoga o token JWT atual, invalidando-o imediatamente.

    **Segurança:**
    - O token é adicionado à blacklist e não poderá mais ser usado
    - Tokens revogados são armazenados até sua data de expiração natural
    - Para acessar o sistema novamente, faça login e obtenha um novo token

    **Header Necessário:**
    ```
    Authorization: Bearer SEU_TOKEN_JWT
    ```

    **Exemplo:**
    ```bash
    curl -X POST "http://localhost:8000/api/v1/auth/logout" \\
         -H "Authorization: Bearer eyJhbGciOiJIUz..."
    ```
    """,
    responses={
        204: {"description": "Logout realizado com sucesso - Token revogado"},
        401: {"description": "Token ausente, inválido ou já expirado", "model": ErrorResponse},
        500: {"description": "Erro interno do servidor", "model": ErrorResponse},
    },
)
async def logout(
    request: "Request",
    current_user=Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    import asyncio

    payload = getattr(request.state, "jwt_payload", None)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    from datetime import datetime as _dt, timezone as _tz

    expires_at = _dt.fromtimestamp(exp, tz=_tz.utc)
    loop = asyncio.get_running_loop()

    # Revoga token em thread pool
    await loop.run_in_executor(
        None, user_service.revoke_token, jti, expires_at
    )
    return None


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Obter dados do usuário autenticado",
    description="""
    Retorna as informações do usuário atualmente autenticado.

    **Uso:**
    - Endpoint útil para validar se o token ainda está válido
    - Use para obter dados atualizados do usuário (nome, email, permissões)
    - Requer token JWT no header Authorization

    **Como usar:**
    1. Faça login em `/auth/login` e copie o token
    2. Clique no botão **🔓 Authorize** no topo
    3. Cole o token e clique em "Authorize"
    4. Teste este endpoint clicando em "Try it out" → "Execute"

    **Exemplo de uso no frontend:**
    ```javascript
    // Verificar se usuário está autenticado
    fetch('http://localhost:8000/api/v1/auth/me', {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    })
    .then(res => res.json())
    .then(user => console.log('Usuário:', user));
    ```
    """,
    responses={
        200: {
            "description": "Dados do usuário autenticado",
            "content": {
                "application/json": {
                    "example": {
                        "id": 1,
                        "email": "joao.silva@empresa.com.br",
                        "name": "João Silva",
                        "is_active": True,
                        "is_admin": False,
                        "created_at": "2025-11-07T14:30:00"
                    }
                }
            }
        },
        401: {"description": "Token ausente, inválido, expirado ou revogado", "model": ErrorResponse},
    },
)
async def me(current_user=Depends(get_current_user)) -> UserPublic:
    return UserPublic(
        id=current_user["id"],
        email=current_user["email"],
        name=current_user.get("name"),
        is_active=bool(current_user.get("is_active")),
        is_admin=bool(current_user.get("is_admin")),
        created_at=datetime.fromisoformat(current_user["created_at"]),
    )
