import json
from pathlib import Path

import pytest
import pytest_asyncio

from biz.database import connection as db_connection
from biz.services.template_skill_service import TemplateSkillService


@pytest_asyncio.fixture
async def temp_db(tmp_path):
    """Provide a isolated database manager for template skill tests."""
    db_file = tmp_path / "skills.db"
    manager = db_connection.DatabaseManager(db_file)
    db_connection._db_manager = manager
    await manager.create_tables()
    try:
        yield manager
    finally:
        await manager.close()
        db_connection._db_manager = None


@pytest.mark.asyncio
async def test_template_skill_service_role_template_update(tmp_path, temp_db, monkeypatch):
    settings_payload = {
        "roles": {
            "education": {"name": "教育专家"},
            "general": {"name": "通用专家"},
        }
    }
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps(settings_payload, ensure_ascii=False), encoding="utf-8"
    )

    from biz.services import template_skill_service as service_module

    monkeypatch.setattr(service_module, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(service_module, "SETTINGS_EXAMPLE_FILE", settings_file)

    service = TemplateSkillService()
    await service.initialize()

    roles = await service.list_roles()
    role_keys = {role["role_key"] for role in roles}
    assert "education" in role_keys

    skill_path = Path("config/template_skills/content_card/SKILL.md")
    skill_markdown = skill_path.read_text(encoding="utf-8")
    updated = await service.update_role_template(
        "education", "content_card", skill_markdown
    )
    assert updated["category"] == "content_card"

    info = await service.get_role_template_info("education", "content_card")
    assert info.get("skill_markdown")
