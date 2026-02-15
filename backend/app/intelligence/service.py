import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies.models import Company
from app.config import settings
from app.intelligence.models import IntelligenceCache
from app.signals.models import HealthScore, SignalEvent
from app.software.models import SoftwareRegistration

logger = structlog.get_logger()

K_ANONYMITY = settings.K_ANONYMITY_THRESHOLD


def _call_llm(prompt: str, max_tokens: int = 4096) -> str:
    """Call Claude directly via the Anthropic SDK (synchronous)."""
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _extract_json(text: str) -> dict | list | None:
    """Extract JSON from LLM response that may contain markdown fences."""
    import re

    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    code_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if code_match:
        try:
            return json.loads(code_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try to find array or object
    for pattern in [r"\[.*\]", r"\{.*\}"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

    return None


async def rebuild_intelligence_index(db: AsyncSession) -> int:
    """Rebuild the entire intelligence cache: aggregation + LLM categorization + CUJ derivation."""

    # 1. Group software by (vendor, software), count distinct companies, apply k-anonymity
    group_q = (
        select(
            SoftwareRegistration.vendor_name,
            SoftwareRegistration.software_name,
            func.count(func.distinct(SoftwareRegistration.company_id)).label("company_count"),
        )
        .where(SoftwareRegistration.status == "active")
        .group_by(SoftwareRegistration.vendor_name, SoftwareRegistration.software_name)
        .having(func.count(func.distinct(SoftwareRegistration.company_id)) >= K_ANONYMITY)
    )
    group_result = await db.execute(group_q)
    qualifying = group_result.all()

    if not qualifying:
        logger.info("intelligence_rebuild_no_qualifying_software", k=K_ANONYMITY)
        return 0

    entries: list[dict] = []
    products_for_categorization: list[dict] = []

    for row in qualifying:
        vendor = row.vendor_name
        software = row.software_name
        count = row.company_count

        # Avg health score
        avg_q = (
            select(func.avg(HealthScore.score))
            .join(SoftwareRegistration, HealthScore.software_id == SoftwareRegistration.id)
            .where(
                SoftwareRegistration.vendor_name == vendor,
                SoftwareRegistration.software_name == software,
            )
        )
        avg_result = await db.execute(avg_q)
        avg_score = avg_result.scalar_one_or_none()

        # Industry distribution
        industry_q = (
            select(Company.industry, func.count().label("count"))
            .join(SoftwareRegistration, Company.id == SoftwareRegistration.company_id)
            .where(
                SoftwareRegistration.vendor_name == vendor,
                SoftwareRegistration.software_name == software,
                SoftwareRegistration.status == "active",
            )
            .group_by(Company.industry)
        )
        industry_result = await db.execute(industry_q)
        industry_dist = [
            {"label": r.industry or "Unknown", "count": r.count}
            for r in industry_result.all()
        ]

        # Size distribution
        size_q = (
            select(Company.company_size, func.count().label("count"))
            .join(SoftwareRegistration, Company.id == SoftwareRegistration.company_id)
            .where(
                SoftwareRegistration.vendor_name == vendor,
                SoftwareRegistration.software_name == software,
                SoftwareRegistration.status == "active",
            )
            .group_by(Company.company_size)
        )
        size_result = await db.execute(size_q)
        size_dist = [
            {"label": r.company_size or "Unknown", "count": r.count}
            for r in size_result.all()
        ]

        # Gather intended uses for categorization
        uses_q = (
            select(SoftwareRegistration.intended_use)
            .where(
                SoftwareRegistration.vendor_name == vendor,
                SoftwareRegistration.software_name == software,
                SoftwareRegistration.intended_use.isnot(None),
            )
        )
        uses_result = await db.execute(uses_q)
        intended_uses = [r[0] for r in uses_result.all() if r[0]]

        products_for_categorization.append({
            "vendor": vendor,
            "software": software,
            "intended_uses": intended_uses[:5],
        })

        entries.append({
            "vendor_name": vendor,
            "software_name": software,
            "avg_health_score": round(avg_score) if avg_score else None,
            "company_count": count,
            "industry_distribution": industry_dist,
            "size_distribution": size_dist,
        })

    # 2. LLM auto-categorize (batch)
    categories_map = await _auto_categorize(products_for_categorization)

    # 3. LLM CUJ derivation (per software)
    for entry in entries:
        entry["auto_category"] = categories_map.get(
            f"{entry['vendor_name']}|{entry['software_name']}"
        )
        cuj = await _derive_cuj(db, entry["vendor_name"], entry["software_name"])
        entry["cuj_data"] = cuj

    # 4. Upsert into IntelligenceCache
    # Clear existing (bulk delete + flush so inserts don't collide)
    from sqlalchemy import delete as sa_delete
    await db.execute(sa_delete(IntelligenceCache))
    await db.flush()

    now = datetime.now(timezone.utc)
    for entry in entries:
        cache = IntelligenceCache(
            vendor_name=entry["vendor_name"],
            software_name=entry["software_name"],
            auto_category=entry.get("auto_category"),
            avg_health_score=entry.get("avg_health_score"),
            company_count=entry["company_count"],
            industry_distribution=entry["industry_distribution"],
            size_distribution=entry["size_distribution"],
            cuj_data=entry.get("cuj_data"),
            computed_at=now,
        )
        db.add(cache)

    await db.commit()
    logger.info("intelligence_index_rebuilt", entries=len(entries))
    return len(entries)


async def _auto_categorize(products: list[dict]) -> dict[str, str]:
    """Use LLM to auto-categorize software products. Returns vendor|software -> category map."""
    if not products or not settings.ANTHROPIC_API_KEY:
        return {}

    product_lines = []
    for p in products:
        uses = ", ".join(f'"{u}"' for u in p["intended_uses"]) if p["intended_uses"] else "not specified"
        product_lines.append(f'- {p["software"]} by {p["vendor"]} (intended uses: {uses})')

    prompt = (
        "Given these software products used across multiple companies, assign each a product category.\n"
        "Categories should be specific but not overly narrow (e.g., 'Cloud Infrastructure', 'CI/CD Pipeline', "
        "'Team Communication', 'Incident Management', 'Project Management', 'Monitoring & Observability').\n\n"
        "Products:\n"
        + "\n".join(product_lines)
        + "\n\nReturn ONLY a JSON array: "
        '[{"vendor": "...", "software": "...", "category": "..."}]'
    )

    try:
        raw = _call_llm(prompt, max_tokens=2048)
        parsed = _extract_json(raw)
        if isinstance(parsed, list):
            return {
                f"{item['vendor']}|{item['software']}": item["category"]
                for item in parsed
                if isinstance(item, dict) and "vendor" in item and "software" in item and "category" in item
            }
    except Exception as e:
        logger.warning("auto_categorize_failed", error=str(e))

    return {}


async def _derive_cuj(db: AsyncSession, vendor_name: str, software_name: str) -> dict | None:
    """Use LLM to derive product-specific CUJ stages from signal data."""

    # Get all software registration IDs + company IDs for this vendor/software
    regs_q = select(
        SoftwareRegistration.id,
        SoftwareRegistration.company_id,
    ).where(
        SoftwareRegistration.vendor_name == vendor_name,
        SoftwareRegistration.software_name == software_name,
        SoftwareRegistration.status == "active",
    )
    regs = (await db.execute(regs_q)).all()
    if not regs:
        return None

    sw_ids = [r.id for r in regs]
    company_ids = list(set(r.company_id for r in regs))
    sw_to_company = {r.id: r.company_id for r in regs}

    # Get company metadata
    companies_q = select(Company.id, Company.industry, Company.company_size).where(
        Company.id.in_(company_ids)
    )
    company_info = {
        r.id: {"industry": r.industry or "Unknown", "size": r.company_size or "Unknown"}
        for r in (await db.execute(companies_q)).all()
    }

    # Fetch all signals
    signals_q = (
        select(SignalEvent)
        .where(SignalEvent.software_id.in_(sw_ids))
        .order_by(SignalEvent.occurred_at.asc())
    )
    signals = list((await db.execute(signals_q)).scalars().all())

    if not signals:
        return None

    # Build anonymized company labels
    company_labels = {}
    label_to_id = {}
    for idx, cid in enumerate(company_ids):
        label = f"Company {chr(65 + idx)}" if idx < 26 else f"Company {idx + 1}"
        company_labels[cid] = label
        label_to_id[label] = str(cid)

    # Build signal groups by company
    company_signals: dict[uuid.UUID, list[dict]] = defaultdict(list)
    for sig in signals:
        cid = sw_to_company.get(sig.software_id)
        if cid:
            sig_label = (
                f"[{sig.occurred_at.strftime('%Y-%m-%d')}] "
                f"event_type={sig.event_type}, "
                f'title="{sig.title or "N/A"}", '
                f"severity={sig.severity or 'unknown'}"
            )
            company_signals[cid].append({
                "label": sig_label,
                "id": str(sig.id),
                "date": sig.occurred_at.strftime("%Y-%m-%d"),
            })

    # Build prompt
    sections = []
    for cid in company_ids:
        label = company_labels[cid]
        info = company_info.get(cid, {"industry": "Unknown", "size": "Unknown"})
        sigs = company_signals.get(cid, [])
        sig_lines = "\n".join(f"  - {s['label']}" for s in sigs[:30])
        sections.append(f"{label} ({info['industry']}, {info['size']}):\n{sig_lines}")

    if not settings.ANTHROPIC_API_KEY:
        return _fallback_cuj(signals, sw_to_company, company_labels, label_to_id)

    prompt = (
        f"Analyze these operational signals from {len(company_ids)} companies using "
        f"{software_name} by {vendor_name}.\n"
        "Derive the Critical User Journey stages specific to this product — NOT generic stages, "
        "but stages that reflect the actual adoption and usage patterns seen in the data.\n\n"
        "Signals by company:\n"
        + "\n\n".join(sections)
        + "\n\nFor each company's stage assignment, include the date range of the signals "
        "that relate to that stage (use the [YYYY-MM-DD] dates from the signal data).\n\n"
        "Return ONLY a JSON object:\n"
        "{\n"
        '  "stages": [\n'
        '    {"order": 1, "name": "Stage Name", "description": "One sentence description"},\n'
        "    ...\n"
        "  ],\n"
        '  "assignments": {\n'
        '    "Company A": [\n'
        '      {"stage_order": 1, "satisfied": true, "key_signal": "brief summary", '
        '"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"},\n'
        "      ...\n"
        "    ],\n"
        "    ...\n"
        "  }\n"
        "}"
    )

    try:
        raw = _call_llm(prompt, max_tokens=4096)
        parsed = _extract_json(raw)
        if isinstance(parsed, dict) and "stages" in parsed:
            # Map company labels back to real IDs and compute avg durations
            assignments = parsed.get("assignments", {})
            company_satisfaction = {}
            stage_durations: dict[int, list[float]] = defaultdict(list)

            for label, stage_list in assignments.items():
                real_id = label_to_id.get(label)
                if real_id and isinstance(stage_list, list):
                    company_satisfaction[real_id] = {
                        str(s.get("stage_order", 0)): s.get("satisfied", True)
                        for s in stage_list
                        if isinstance(s, dict)
                    }
                    for s in stage_list:
                        if isinstance(s, dict):
                            order = s.get("stage_order", 0)
                            sd = s.get("start_date")
                            ed = s.get("end_date")
                            if sd and ed:
                                try:
                                    start_dt = datetime.strptime(sd, "%Y-%m-%d")
                                    end_dt = datetime.strptime(ed, "%Y-%m-%d")
                                    days = max((end_dt - start_dt).days, 1)
                                    stage_durations[order].append(days)
                                except ValueError:
                                    pass

            # Attach avg_duration_days to stages
            for stage in parsed["stages"]:
                order = stage.get("order", 0)
                durations = stage_durations.get(order, [])
                stage.pop("start_date", None)
                stage.pop("end_date", None)
                if durations:
                    stage["avg_duration_days"] = round(sum(durations) / len(durations), 1)

            return {
                "stages": parsed["stages"],
                "company_satisfaction": company_satisfaction,
                "label_to_id": label_to_id,
            }
    except Exception as e:
        logger.warning("cuj_derivation_failed", error=str(e), vendor=vendor_name, software=software_name)

    return _fallback_cuj(signals, sw_to_company, company_labels, label_to_id)


def _fallback_cuj(
    signals: list[SignalEvent],
    sw_to_company: dict,
    company_labels: dict,
    label_to_id: dict,
) -> dict:
    """Deterministic fallback CUJ when LLM is unavailable."""
    stages = [
        {"order": 1, "name": "Onboarding", "description": "Initial setup and provisioning"},
        {"order": 2, "name": "Integration", "description": "Connecting with existing systems"},
        {"order": 3, "name": "Active Use", "description": "Day-to-day operations"},
        {"order": 4, "name": "Issue Resolution", "description": "Handling incidents and bugs"},
        {"order": 5, "name": "Support", "description": "Vendor support interactions"},
    ]

    # Simple keyword-based assignment
    def _classify(sig: SignalEvent) -> int:
        text = f"{sig.event_type} {sig.title or ''}".lower()
        if any(kw in text for kw in ["setup", "onboard", "install", "provision"]):
            return 1
        if any(kw in text for kw in ["integrat", "connect", "sso", "api", "webhook"]):
            return 2
        if any(kw in text for kw in ["incident", "outage", "error", "fail", "down"]):
            return 4
        if any(kw in text for kw in ["support", "resolved", "ticket resolved", "maintenance"]):
            return 5
        return 3

    company_stages: dict[str, dict[str, bool]] = defaultdict(dict)
    # Track signal dates per (company, stage) to compute avg duration
    company_stage_dates: dict[tuple[str, int], list[datetime]] = defaultdict(list)

    for sig in signals:
        cid = sw_to_company.get(sig.software_id)
        if cid:
            stage = _classify(sig)
            stage_key = str(stage)
            if stage_key not in company_stages[str(cid)]:
                company_stages[str(cid)][stage_key] = True
            if sig.severity in ("critical", "high"):
                company_stages[str(cid)][stage_key] = False
            company_stage_dates[(str(cid), stage)].append(sig.occurred_at)

    # Compute avg_duration_days per stage
    for stage_def in stages:
        order = stage_def["order"]
        durations: list[float] = []
        for (cid, so), dates in company_stage_dates.items():
            if so == order:
                if len(dates) >= 2:
                    days = max((max(dates) - min(dates)).days, 1)
                    durations.append(days)
                else:
                    durations.append(1)
        if durations:
            stage_def["avg_duration_days"] = round(sum(durations) / len(durations), 1)

    return {
        "stages": stages,
        "company_satisfaction": company_stages,
        "label_to_id": label_to_id,
    }


async def get_intelligence_index(
    db: AsyncSession,
    category: str | None = None,
    search: str | None = None,
) -> dict:
    """Read from the intelligence cache, with optional filters."""
    query = select(IntelligenceCache).order_by(IntelligenceCache.avg_health_score.desc().nullslast())

    if category:
        query = query.where(IntelligenceCache.auto_category == category)
    if search:
        like = f"%{search}%"
        query = query.where(
            IntelligenceCache.vendor_name.ilike(like)
            | IntelligenceCache.software_name.ilike(like)
            | IntelligenceCache.auto_category.ilike(like)
        )

    result = await db.execute(query)
    entries = list(result.scalars().all())

    # Get distinct categories
    cat_q = select(IntelligenceCache.auto_category).where(
        IntelligenceCache.auto_category.isnot(None)
    ).distinct()
    cat_result = await db.execute(cat_q)
    categories = sorted([r[0] for r in cat_result.all()])

    return {
        "items": [
            {
                "vendor_name": e.vendor_name,
                "software_name": e.software_name,
                "auto_category": e.auto_category,
                "avg_health_score": e.avg_health_score,
                "company_count": e.company_count,
            }
            for e in entries
        ],
        "categories": categories,
    }


async def get_solution_detail(
    db: AsyncSession,
    vendor_name: str,
    software_name: str,
) -> dict | None:
    """Get full solution detail from cache."""
    result = await db.execute(
        select(IntelligenceCache).where(
            IntelligenceCache.vendor_name == vendor_name,
            IntelligenceCache.software_name == software_name,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        return None

    # Build CUJ response from cuj_data
    cuj = None
    if entry.cuj_data and "stages" in entry.cuj_data:
        satisfaction = entry.cuj_data.get("company_satisfaction", {})
        stages = []
        for stage in entry.cuj_data["stages"]:
            order = stage.get("order", 0)
            satisfied = 0
            dissatisfied = 0
            for _cid, stage_map in satisfaction.items():
                val = stage_map.get(str(order))
                if val is True:
                    satisfied += 1
                elif val is False:
                    dissatisfied += 1
            stages.append({
                "order": order,
                "name": stage.get("name", f"Stage {order}"),
                "description": stage.get("description", ""),
                "satisfied_count": satisfied,
                "dissatisfied_count": dissatisfied,
                "total": satisfied + dissatisfied,
                "avg_duration_days": stage.get("avg_duration_days"),
            })
        cuj = {
            "vendor_name": vendor_name,
            "software_name": software_name,
            "stages": stages,
        }

    return {
        "vendor_name": entry.vendor_name,
        "software_name": entry.software_name,
        "auto_category": entry.auto_category,
        "avg_health_score": entry.avg_health_score,
        "company_count": entry.company_count,
        "industry_distribution": entry.industry_distribution or [],
        "size_distribution": entry.size_distribution or [],
        "cuj": cuj,
    }


async def get_cuj_drilldown(
    db: AsyncSession,
    vendor_name: str,
    software_name: str,
    stage_order: int,
) -> dict | None:
    """Drill down to companies at a specific CUJ stage."""
    # Get cached CUJ data
    result = await db.execute(
        select(IntelligenceCache).where(
            IntelligenceCache.vendor_name == vendor_name,
            IntelligenceCache.software_name == software_name,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry or not entry.cuj_data:
        return None

    cuj_data = entry.cuj_data
    stages = cuj_data.get("stages", [])
    satisfaction = cuj_data.get("company_satisfaction", {})

    # Find stage name
    stage_info = next((s for s in stages if s.get("order") == stage_order), None)
    if not stage_info:
        return None

    # Find companies that participated in this stage
    company_ids_at_stage = []
    for cid, stage_map in satisfaction.items():
        if str(stage_order) in stage_map:
            company_ids_at_stage.append((cid, stage_map[str(stage_order)]))

    if not company_ids_at_stage:
        return {"stage_order": stage_order, "stage_name": stage_info["name"], "companies": []}

    # Get company details
    cid_uuids = [uuid.UUID(cid) for cid, _ in company_ids_at_stage]
    companies_q = select(Company).where(Company.id.in_(cid_uuids))
    companies = {
        str(c.id): c
        for c in (await db.execute(companies_q)).scalars().all()
    }

    # Get signals for these companies
    sw_q = select(SoftwareRegistration.id, SoftwareRegistration.company_id).where(
        SoftwareRegistration.vendor_name == vendor_name,
        SoftwareRegistration.software_name == software_name,
    )
    sw_regs = (await db.execute(sw_q)).all()
    sw_ids_for_companies = {
        str(r.company_id): r.id for r in sw_regs
    }

    result_companies = []
    for cid, is_satisfied in company_ids_at_stage:
        company = companies.get(cid)
        if not company:
            continue

        sw_id = sw_ids_for_companies.get(cid)
        contacts = set()
        if sw_id:
            sig_q = (
                select(SignalEvent)
                .where(SignalEvent.software_id == sw_id)
                .order_by(SignalEvent.occurred_at.desc())
                .limit(20)
            )
            for sig in (await db.execute(sig_q)).scalars().all():
                if sig.event_metadata and isinstance(sig.event_metadata, dict):
                    # Read from merged reporters list first, fall back to single reporter
                    reporters = sig.event_metadata.get("reporters", [])
                    if reporters:
                        for r in reporters:
                            contacts.add(r)
                    else:
                        reporter = sig.event_metadata.get("reporter")
                        if reporter:
                            contacts.add(reporter)

        result_companies.append({
            "company_id": cid,
            "company_name": company.company_name,
            "industry": company.industry,
            "company_size": company.company_size,
            "satisfied": is_satisfied,
            "contacts": sorted(contacts),
        })

    return {
        "stage_order": stage_order,
        "stage_name": stage_info["name"],
        "companies": result_companies,
    }


async def generate_targeted_outreach(
    db: AsyncSession,
    vendor_name: str,
    software_name: str,
    stage_order: int,
    company_id: uuid.UUID,
    contact_name: str | None = None,
) -> dict | None:
    """Generate personalized outreach using LLM, optionally targeted at a specific contact."""
    # Get company
    company = (await db.execute(
        select(Company).where(Company.id == company_id)
    )).scalar_one_or_none()
    if not company:
        return None

    # Get CUJ cache for stage name
    cache = (await db.execute(
        select(IntelligenceCache).where(
            IntelligenceCache.vendor_name == vendor_name,
            IntelligenceCache.software_name == software_name,
        )
    )).scalar_one_or_none()

    stage_name = f"Stage {stage_order}"
    if cache and cache.cuj_data:
        stage_info = next(
            (s for s in cache.cuj_data.get("stages", []) if s.get("order") == stage_order),
            None,
        )
        if stage_info:
            stage_name = stage_info.get("name", stage_name)

    # Get this company's signals
    sw_q = select(SoftwareRegistration.id).where(
        SoftwareRegistration.vendor_name == vendor_name,
        SoftwareRegistration.software_name == software_name,
        SoftwareRegistration.company_id == company_id,
    )
    sw_result = await db.execute(sw_q)
    sw_row = sw_result.first()
    if not sw_row:
        return None

    sig_q = (
        select(SignalEvent)
        .where(SignalEvent.software_id == sw_row[0])
        .order_by(SignalEvent.occurred_at.desc())
        .limit(15)
    )
    all_signals = list((await db.execute(sig_q)).scalars().all())

    # Filter to contact's signals if specified
    if contact_name:
        contact_signals = [
            s for s in all_signals
            if s.event_metadata and isinstance(s.event_metadata, dict)
            and (
                s.event_metadata.get("reporter") == contact_name
                or contact_name in s.event_metadata.get("reporters", [])
            )
        ]
    else:
        contact_signals = all_signals

    pain_signals = [s for s in contact_signals if s.severity in ("critical", "high")]
    pain_points = [s.title or s.event_type for s in pain_signals]

    # Build context lines (include all of this contact's signals)
    signal_lines = []
    for s in contact_signals[:10]:
        line = f"- [{s.occurred_at.strftime('%Y-%m-%d')}] {s.title or s.event_type} (severity: {s.severity or 'unknown'})"
        signal_lines.append(line)
    signal_context = "\n".join(signal_lines) if signal_lines else "- No specific signals found"

    greeting_name = contact_name or f"{company.company_name} team"

    if not settings.ANTHROPIC_API_KEY:
        return {
            "company_name": company.company_name,
            "contact_name": contact_name,
            "generated_message": (
                f"Hi {greeting_name},\n\n"
                f"We noticed your team has been experiencing challenges with {software_name} "
                f"during the {stage_name} phase. Specifically: {', '.join(pain_points[:3]) or 'various issues'}.\n\n"
                f"We'd love to discuss how we can help improve your experience.\n\n"
                f"Best regards"
            ),
            "pain_points": pain_points,
        }

    contact_context = ""
    if contact_name:
        contact_context = (
            f"This message is specifically for {contact_name}, who has been directly involved "
            f"in the following events:\n{signal_context}\n\n"
            "Reference their specific experiences naturally without being overly detailed about "
            "internal data — they should feel recognized, not surveilled.\n\n"
        )

    prompt = (
        f"Generate a personalized outreach message for {greeting_name} at {company.company_name} "
        f"({company.industry or 'Unknown'} industry, {company.company_size or 'Unknown'} size) "
        f"regarding their experience with {software_name} by {vendor_name} "
        f'at the "{stage_name}" stage of their journey.\n\n'
        f"{contact_context}"
        f"Their notable signals:\n{signal_context}\n\n"
        "Write 2-3 concise paragraphs that:\n"
        "1. Acknowledge their specific challenges naturally\n"
        "2. Provide relevant context about how other teams have addressed similar issues\n"
        "3. Suggest a specific next step or meeting\n\n"
        "Professional but warm tone. No subject line — just the message body. "
        f"Address it to {greeting_name}."
    )

    try:
        message = _call_llm(prompt, max_tokens=512)
    except Exception as e:
        logger.warning("outreach_generation_failed", error=str(e))
        message = (
            f"Hi {greeting_name},\n\n"
            f"We noticed challenges with {software_name} during {stage_name}. "
            f"We'd love to help.\n\nBest regards"
        )

    return {
        "company_name": company.company_name,
        "contact_name": contact_name,
        "generated_message": message,
        "pain_points": pain_points,
    }
