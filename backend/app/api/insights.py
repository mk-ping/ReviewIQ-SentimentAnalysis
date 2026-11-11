from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.true_rating import true_rating

router = APIRouter(tags=["insights"])


@router.get("/true-rating")
async def get_true_rating(session: AsyncSession = Depends(get_session)):
    return {"products": await true_rating(session)}
