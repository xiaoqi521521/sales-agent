from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt import InvalidTokenError

from app.core.config import get_settings


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """创建 JWT 访问令牌
    
    Args:
        data: 要编码到令牌中的用户数据字典，通常包含用户ID、用户名等信息
        expires_delta: 可选的过期时间增量，如果不提供则使用配置中的默认值
        
    Returns:
        str: 编码后的 JWT token 字符串
        
    Example:
        >>> token = create_access_token({"sub": "123", "username": "john"})
    """
    settings = get_settings()
    # 计算令牌过期时间：当前UTC时间 + 过期时长
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    )
    payload = data.copy()
    payload.update({"exp": expire})  # 添加标准的JWT过期时间声明
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """解码并验证 JWT 访问令牌
    
    Args:
        token: 需要解码的 JWT token 字符串
        
    Returns:
        dict[str, Any]: 解码后的payload字典，包含用户数据和标准声明
        
    Raises:
        ValueError: 当token无效或格式错误时抛出异常
        
    Example:
        >>> payload = decode_access_token(token)
        >>> rep_id = payload.get("sub")
    """
    settings = get_settings()
    try:
        # 验证签名并解码token，自动检查过期时间
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except InvalidTokenError as exc:
        raise ValueError("invalid token") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid token payload")
    return payload
