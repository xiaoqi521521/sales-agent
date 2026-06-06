"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runtime import SalesAgentRuntime
from app.core.auth_context import CurrentUser
from app.core.database import get_db_session
from app.core.security import decode_access_token
from app.repositories.sales_rep_repository import SalesRepRepository


# OAuth2 密码 bearer 认证方案，指定 token 获取端点
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CurrentUser:
    """获取并验证当前用户身份（FastAPI 依赖注入）
    
    从请求头中提取 JWT token，解码并验证用户身份，返回当前用户上下文。
    用于需要认证的路由保护。
    
    Args:
        token: 从请求头 Authorization: Bearer 中自动提取的 JWT token 字符串
        session: 异步数据库会话，通过依赖注入获取
        
    Returns:
        CurrentUser: 当前用户的上下文对象，包含用户名、角色、区域和销售员 ID 等信息
        
    Raises:
        HTTPException: 
            - 401 UNAUTHORIZED: token 无效、过期或无法解析
            - 401 UNAUTHORIZED: 数据库中找不到对应的销售人员记录
    """
    # 定义统一的认证失败异常
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 解码并验证 JWT token（自动检查签名和过期时间）
        payload = decode_access_token(token)
        # 从 token payload 中提取销售员 ID（sub 字段）
        rep_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        # token 格式错误或解析失败
        raise credentials_exception from None

    # 从数据库中查询销售人员信息，验证用户是否存在
    rep = await SalesRepRepository().find_by_id(session, rep_id)
    if rep is None:
        # 用户不存在或已被删除
        raise credentials_exception
    
    # 构建并返回当前用户上下文对象
    return CurrentUser.from_sales_rep(rep)


async def get_sales_agent_runtime(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> SalesAgentRuntime:
    """获取销售 Agent 运行时实例（FastAPI 依赖注入）
    
    创建并返回配置好数据库会话和用户上下文的 Agent 运行时实例。
    用于需要调用 AI Agent 的路由。
    """
    return SalesAgentRuntime(session=session, current_user=current_user)
