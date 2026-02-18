"""Signal grouping utilities for the hierarchical analysis pipeline.

Groups signals into sub-categories using classifier metadata (not keyword scanning).
"""

from collections import defaultdict

from app.signals.models import SignalEvent


def group_by_stage(
    signals: list[SignalEvent],
) -> dict[str, list[SignalEvent]]:
    """Group signals by ``stage_topic`` classifier metadata.

    Returns ``{stage_name: [signals]}``.  Signals without a ``stage_topic``
    tag default to ``"productive"``.
    """
    groups: dict[str, list[SignalEvent]] = defaultdict(list)
    for sig in signals:
        meta = sig.event_metadata or {}
        stage = meta.get("stage_topic", "productive")
        groups[stage].append(sig)
    return dict(groups)
