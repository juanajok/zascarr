"""Router de aceptación legal — /api/legal. Ver services/legal.py para
qué rutas exigen esta aceptación y por qué (solo las que disparan
búsqueda/descarga, no toda la app)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from secuenciarr.database import get_db
from secuenciarr.services.legal import acknowledge, current_legal_version, get_acknowledgment

router = APIRouter(prefix="/api/legal", tags=["legal"])


class LegalAccept(BaseModel):
    acknowledged: bool = False


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db)):
    ack = await get_acknowledgment(db)
    return {
        "accepted": ack is not None,
        "accepted_at": ack.accepted_at.isoformat() if ack else None,
        "legal_version": current_legal_version(),
    }


@router.post("/accept", status_code=201)
async def accept(data: LegalAccept, db: AsyncSession = Depends(get_db)):
    if not data.acknowledged:
        raise HTTPException(status_code=400, detail="Debes marcar acknowledged=true")
    ack = await acknowledge(db)
    return {"accepted": True, "accepted_at": ack.accepted_at.isoformat(), "legal_version": ack.legal_version}
