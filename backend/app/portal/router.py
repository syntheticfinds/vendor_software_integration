from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.portal.schemas import ChatRequest, ChatResponse, PublicSoftwareResponse
from app.portal.service import get_public_index, get_public_software, handle_chat, rebuild_public_index

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/software-index", response_model=list[PublicSoftwareResponse])
async def list_public_software(db: AsyncSession = Depends(get_db)):
    """Public endpoint — no auth required. Returns aggregated software data."""
    entries = await get_public_index(db)
    return [PublicSoftwareResponse.model_validate(e) for e in entries]


@router.get("/software/{vendor_name}/{software_name}", response_model=PublicSoftwareResponse)
async def get_software_profile(
    vendor_name: str,
    software_name: str,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint — get a specific software's public profile."""
    entry = await get_public_software(db, vendor_name, software_name)
    if not entry:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Software not found in public index")
    return PublicSoftwareResponse.model_validate(entry)


@router.post("/rebuild-index")
async def rebuild_index(db: AsyncSession = Depends(get_db)):
    """Rebuild the public software index (admin operation)."""
    count = await rebuild_public_index(db)
    return {"status": "rebuilt", "entries": count}


@router.post("/chat", response_model=ChatResponse)
async def chat(
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Public chatbot endpoint — no auth required."""
    result = await handle_chat(db, data.message, data.session_token)
    return ChatResponse(**result)
