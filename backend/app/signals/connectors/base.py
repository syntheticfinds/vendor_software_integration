import uuid
from abc import ABC, abstractmethod
from datetime import datetime

from app.signals.models import SignalEvent


class DataConnector(ABC):
    source_type: str

    @abstractmethod
    async def fetch_events(
        self,
        company_id: uuid.UUID,
        software_id: uuid.UUID,
        since: datetime | None = None,
    ) -> list[SignalEvent]:
        pass
