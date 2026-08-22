"""
Tenant (company) config persistence.
Simple JSON-file based store — no external DB needed for the demo deployment.
Each tenant = one company using BrandBot to power their custom chatbot.
"""

import json
import os
import uuid
from typing import Any

TENANTS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "tenants.json")
os.makedirs(os.path.dirname(TENANTS_FILE), exist_ok=True)


def _load_all() -> dict[str, Any]:
    if not os.path.exists(TENANTS_FILE):
        return {}
    with open(TENANTS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save_all(data: dict[str, Any]) -> None:
    with open(TENANTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def create_tenant(name: str, brand_color: str = "#4F46E5", model: str = "openai/gpt-oss-20b") -> str:
    tenants = _load_all()
    tenant_id = str(uuid.uuid4())[:8]
    tenants[tenant_id] = {
        "id": tenant_id,
        "name": name,
        "brand_color": brand_color,
        "model": model,
        "custom_tools": [],
        "doc_count": 0,
        "query_count": 0,
    }
    _save_all(tenants)
    return tenant_id


def get_tenant(tenant_id: str) -> dict[str, Any] | None:
    return _load_all().get(tenant_id)


def list_tenants() -> dict[str, Any]:
    return _load_all()


def update_tenant(tenant_id: str, **kwargs) -> None:
    tenants = _load_all()
    if tenant_id in tenants:
        tenants[tenant_id].update(kwargs)
        _save_all(tenants)


def add_custom_tool(tenant_id: str, name: str, description: str, url: str, method: str = "GET") -> None:
    tenants = _load_all()
    if tenant_id in tenants:
        tenants[tenant_id]["custom_tools"].append(
            {"name": name, "description": description, "url": url, "method": method}
        )
        _save_all(tenants)


def increment_doc_count(tenant_id: str, n: int = 1) -> None:
    tenants = _load_all()
    if tenant_id in tenants:
        tenants[tenant_id]["doc_count"] = tenants[tenant_id].get("doc_count", 0) + n
        _save_all(tenants)


def increment_query_count(tenant_id: str) -> None:
    tenants = _load_all()
    if tenant_id in tenants:
        tenants[tenant_id]["query_count"] = tenants[tenant_id].get("query_count", 0) + 1
        _save_all(tenants)


def delete_tenant(tenant_id: str) -> None:
    tenants = _load_all()
    if tenant_id in tenants:
        del tenants[tenant_id]
        _save_all(tenants)
