import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.portal.models import ChatMessage, ChatSession, PublicSoftwareIndex
from app.signals.models import HealthScore
from app.software.models import SoftwareRegistration

logger = structlog.get_logger()

K_ANONYMITY = settings.K_ANONYMITY_THRESHOLD


async def rebuild_public_index(db: AsyncSession) -> int:
    """Rebuild the public software index with k-anonymity filtering."""
    # Aggregate: group by vendor+software, count distinct companies, avg health score
    # Only include if company_count >= K_ANONYMITY
    query = (
        select(
            SoftwareRegistration.vendor_name,
            SoftwareRegistration.software_name,
            func.count(func.distinct(SoftwareRegistration.company_id)).label("company_count"),
        )
        .where(SoftwareRegistration.status == "active")
        .group_by(SoftwareRegistration.vendor_name, SoftwareRegistration.software_name)
        .having(func.count(func.distinct(SoftwareRegistration.company_id)) >= K_ANONYMITY)
    )

    result = await db.execute(query)
    rows = result.all()

    # Clear existing index
    existing = await db.execute(select(PublicSoftwareIndex))
    for entry in existing.scalars().all():
        await db.delete(entry)

    count = 0
    for row in rows:
        # Get avg health score across all companies for this software
        avg_score_q = (
            select(func.avg(HealthScore.score))
            .join(SoftwareRegistration, HealthScore.software_id == SoftwareRegistration.id)
            .where(
                SoftwareRegistration.vendor_name == row.vendor_name,
                SoftwareRegistration.software_name == row.software_name,
            )
        )
        avg_result = await db.execute(avg_score_q)
        avg_score = avg_result.scalar_one_or_none()

        entry = PublicSoftwareIndex(
            vendor_name=row.vendor_name,
            software_name=row.software_name,
            avg_health_score=round(avg_score) if avg_score else None,
            company_count=row.company_count,
        )
        db.add(entry)
        count += 1

    await db.commit()
    logger.info("public_index_rebuilt", entries=count, k_anonymity=K_ANONYMITY)
    return count


async def get_public_index(db: AsyncSession) -> list[PublicSoftwareIndex]:
    result = await db.execute(
        select(PublicSoftwareIndex).order_by(PublicSoftwareIndex.avg_health_score.desc().nullslast())
    )
    return list(result.scalars().all())


async def get_public_software(
    db: AsyncSession, vendor_name: str, software_name: str
) -> PublicSoftwareIndex | None:
    result = await db.execute(
        select(PublicSoftwareIndex).where(
            PublicSoftwareIndex.vendor_name == vendor_name,
            PublicSoftwareIndex.software_name == software_name,
        )
    )
    return result.scalar_one_or_none()


async def get_or_create_session(db: AsyncSession, session_token: str | None) -> ChatSession:
    if session_token:
        result = await db.execute(
            select(ChatSession).where(ChatSession.session_token == session_token)
        )
        session = result.scalar_one_or_none()
        if session:
            return session

    session = ChatSession(session_token=uuid.uuid4().hex)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def save_chat_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    role: str,
    content: str,
    citations: dict | None = None,
) -> ChatMessage:
    msg = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        citations=citations,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def get_chat_history(db: AsyncSession, session_id: uuid.UUID) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return list(result.scalars().all())


async def handle_chat(db: AsyncSession, message: str, session_token: str | None) -> dict:
    """Process a chat message — search public index and generate a response."""
    session = await get_or_create_session(db, session_token)

    # Save user message
    await save_chat_message(db, session.id, "user", message)

    # Search the public index for relevant software
    all_entries = await get_public_index(db)

    # Simple keyword search over the index
    keywords = message.lower().split()
    matches = []
    for entry in all_entries:
        text = f"{entry.vendor_name} {entry.software_name} {entry.common_issues or ''} {entry.sentiment_summary or ''}".lower()
        if any(kw in text for kw in keywords):
            matches.append(entry)

    # Build response
    citations = []
    if matches:
        parts = []
        for m in matches[:5]:
            score_str = f"Health Score: {m.avg_health_score}/100" if m.avg_health_score else "No health data"
            parts.append(
                f"**{m.software_name}** by {m.vendor_name} — {score_str}, "
                f"used by {m.company_count} companies."
            )
            citations.append({
                "vendor": m.vendor_name,
                "software": m.software_name,
                "score": m.avg_health_score,
            })
        reply = (
            f"Based on aggregated data from our platform, here's what I found:\n\n"
            + "\n\n".join(parts)
        )
    else:
        # Try to provide a helpful response even without matches
        if all_entries:
            top = all_entries[:3]
            reply = (
                f"I couldn't find specific results for '{message}'. "
                f"Here are the top-rated software integrations in our index:\n\n"
                + "\n".join(
                    f"- **{e.software_name}** by {e.vendor_name} "
                    f"(Score: {e.avg_health_score or 'N/A'})"
                    for e in top
                )
            )
        else:
            reply = (
                "I don't have enough aggregated data yet to answer that question. "
                "The public software index requires data from multiple companies "
                "to ensure privacy (k-anonymity)."
            )

    # Save assistant response
    await save_chat_message(db, session.id, "assistant", reply, {"citations": citations})

    return {
        "reply": reply,
        "citations": citations,
        "session_token": session.session_token,
    }
