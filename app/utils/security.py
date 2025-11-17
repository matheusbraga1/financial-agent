import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from passlib.context import CryptContext

from app.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ===== Password Management =====

def hash_password(password: str) -> str:
    """
    Hash de senha com bcrypt.
    
    Valida comprimento e aplica hash seguro.
    
    Args:
        password: Senha em texto plano
        
    Returns:
        Hash bcrypt da senha
        
    Raises:
        ValueError: Se senha for muito curta ou muito longa
    """
    # Validar comprimento
    if len(password) < 8:
        raise ValueError(
            "Senha muito curta. Mínimo de 8 caracteres necessário."
        )
    
    if len(password) > 72:
        raise ValueError(
            "Senha muito longa. Máximo de 72 caracteres permitido."
        )

    # Configurar rounds baseado no ambiente
    rounds = 10 if settings.debug else 12

    return pwd_context.using(bcrypt__rounds=rounds).hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifica se a senha corresponde ao hash.
    
    Args:
        plain_password: Senha em texto plano
        hashed_password: Hash bcrypt armazenado
        
    Returns:
        True se a senha está correta, False caso contrário
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Erro ao verificar senha: {e}")
        return False


# ===== JWT Token Management =====

def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Cria access token JWT.
    
    Args:
        data: Dados para incluir no token (deve conter 'sub' como user_id)
        expires_delta: Tempo de expiração customizado (opcional)
        
    Returns:
        Token JWT codificado
    """
    from app.presentation.api.dependencies import get_jwt_handler
    
    jwt_handler = get_jwt_handler()
    
    user_id = data.get("sub")
    email = data.get("email", "")
    username = data.get("username", "")
    
    # JWTHandler retorna (token, jti)
    token, jti = jwt_handler.create_access_token(
        user_id=user_id,
        email=email,
        roles=[],
        permissions=[],
        additional_claims={"username": username}
    )
    
    return token


def create_refresh_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Cria refresh token JWT.
    
    IMPORTANTE: O token é automaticamente armazenado no Redis pelo JWTHandler.
    
    Args:
        data: Dados para incluir no token (deve conter 'sub' como user_id)
        expires_delta: Tempo de expiração customizado (opcional)
        
    Returns:
        Refresh token JWT codificado
    """
    from app.presentation.api.dependencies import get_jwt_handler
    
    jwt_handler = get_jwt_handler()
    
    user_id = data.get("sub")
    
    # JWTHandler retorna (token, jti) e JÁ armazena no Redis
    token, jti = jwt_handler.create_refresh_token(user_id=user_id)
    
    return token


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodifica e valida access token.
    
    Args:
        token: Token JWT para decodificar
        
    Returns:
        Payload do token se válido, None caso contrário
    """
    from app.presentation.api.dependencies import get_jwt_handler
    
    jwt_handler = get_jwt_handler()
    token_data = jwt_handler.decode_token(token)
    
    if not token_data:
        return None
    
    if token_data.type != "access":
        logger.warning("Token não é do tipo 'access'")
        return None
    
    # Retornar formato compatível com código existente
    return {
        "sub": token_data.sub,
        "email": token_data.email,
        "username": token_data.sub,  # Fallback se não tiver username
        "type": token_data.type,
    }


def decode_refresh_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodifica e valida refresh token.
    
    Args:
        token: Refresh token JWT para decodificar
        
    Returns:
        Payload do token se válido, None caso contrário
    """
    from app.presentation.api.dependencies import get_jwt_handler
    
    jwt_handler = get_jwt_handler()
    token_data = jwt_handler.decode_token(token)
    
    if not token_data:
        return None
    
    if token_data.type != "refresh":
        logger.warning("Token não é do tipo 'refresh'")
        return None
    
    # Retornar formato compatível com código existente
    return {
        "sub": token_data.sub,
        "type": token_data.type,
    }


def revoke_token(token: str) -> bool:
    """
    Revoga token adicionando à blacklist no Redis.
    
    Permite logout efetivo e invalidação imediata de tokens.
    
    Args:
        token: Token JWT para revogar
        
    Returns:
        True se token foi revogado com sucesso, False caso contrário
    """
    from app.presentation.api.dependencies import get_jwt_handler
    
    jwt_handler = get_jwt_handler()
    
    # Decodificar token para obter JTI e expiração
    token_data = jwt_handler.decode_token(token)
    
    if not token_data or not token_data.jti or not token_data.exp:
        logger.warning("Token inválido ou sem JTI/exp para revogação")
        return False
    
    # Adicionar à blacklist
    success = jwt_handler.revoke_token(token_data.jti, token_data.exp)
    
    if success:
        logger.info(f"Token revogado com sucesso: jti={token_data.jti}")
    else:
        logger.warning(f"Falha ao revogar token: jti={token_data.jti}")
    
    return success