import json
import uuid

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.monitoring.models import MonitoredEmail


class EmailFetchInput(BaseModel):
    company_id: str = Field(description="Company UUID to fetch unprocessed emails for")


class EmailFetchTool(BaseTool):
    name: str = "fetch_unprocessed_emails"
    description: str = "Fetch unprocessed emails from the monitoring queue for a company. Returns a JSON array of email objects with id, sender, subject, body_snippet, received_at fields."
    args_schema: type[BaseModel] = EmailFetchInput

    db_session: object = None

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, company_id: str) -> str:
        # This tool is called synchronously by CrewAI.
        # We store pre-fetched emails in the tool instance to avoid async issues.
        if hasattr(self, '_cached_emails'):
            return json.dumps(self._cached_emails)
        return json.dumps([])


class SoftwareRegistryInput(BaseModel):
    company_id: str = Field(description="Company UUID")
    vendor_name: str = Field(description="Vendor name to check")
    software_name: str = Field(description="Software name to check")


class SoftwareRegistryTool(BaseTool):
    name: str = "check_software_registry"
    description: str = "Check if a specific vendor's software is already registered for this company. Returns JSON with already_registered boolean."
    args_schema: type[BaseModel] = SoftwareRegistryInput

    _registered_software: list = []

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, company_id: str, vendor_name: str, software_name: str) -> str:
        # Check against pre-loaded registered software list
        for sw in self._registered_software:
            if (sw["vendor_name"].lower() == vendor_name.lower()
                    and sw["software_name"].lower() == software_name.lower()):
                return json.dumps({"already_registered": True, "registration_id": sw["id"]})
        return json.dumps({"already_registered": False})
