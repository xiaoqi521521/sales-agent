from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_context import CurrentUser
from app.core.database import get_db_session
from app.core.security import create_access_token
from app.repositories.sales_rep_repository import SalesRepRepository
from app.schemas.auth import CurrentUserDTO, LoginRequest, LoginResponse


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LoginResponse:
    rep = await SalesRepRepository().find_by_id(session, request.rep_id)
    if rep is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sales rep not found")

    current_user = CurrentUser.from_sales_rep(rep)
    token = create_access_token(
        {
            "sub": str(current_user.rep_id),
            "role": current_user.role,
            "region_id": current_user.region_id,
        }
    )
    return LoginResponse(
        access_token=token,
        user=CurrentUserDTO(
            rep_id=current_user.rep_id,
            username=current_user.username,
            role=current_user.role,
            region_id=current_user.region_id,
        ),
    )
