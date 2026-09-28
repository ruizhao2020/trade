"""主周期默认值在模型、schema 与建表 SQL 三处必须一致。

历史上 models/template.py 与 SQL 是 '1d'，而两个 schema 是 '15m'，
导致不显式传 primary_tf 的创建路径（脚本、新接入的客户端）会拿到 15m。
"""

import re
from pathlib import Path

from app.models.template import Template
from app.schemas.signal import ConditionTemplateSchema
from app.schemas.template import TemplateCreate

SERVER_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILES = [
    SERVER_ROOT / "database" / "mysql" / "001_app_schema.sql",
    SERVER_ROOT / "database" / "sqlite" / "001_app_schema.sql",
]
EXPECTED_DEFAULT = "1d"


def _minimal_condition_group() -> dict:
    return {
        "id": "g1",
        "conditions": [{
            "id": "c1",
            "name": "收盘价大于0",
            "left": {"source": "price", "field": "close"},
            "operator": "gt",
            "right": {"source": "constant", "value": 0},
        }],
    }


def test_template_create_schema_defaults_to_daily():
    created = TemplateCreate(id="tpl_1", name="测试", condition_groups=[])

    assert created.primary_tf == EXPECTED_DEFAULT


def test_condition_template_schema_defaults_to_daily():
    template = ConditionTemplateSchema(
        id="tpl_1", name="测试", logic="AND",
        condition_groups=[_minimal_condition_group()],
    )

    assert template.primary_tf == EXPECTED_DEFAULT


def test_orm_model_defaults_to_daily():
    assert Template.__table__.c.primary_tf.default.arg == EXPECTED_DEFAULT


def test_schema_sql_defaults_to_daily():
    for path in SCHEMA_FILES:
        sql = path.read_text(encoding="utf-8")
        match = re.search(r"primary_tf\s+VARCHAR\(\d+\)\s+NOT NULL\s+DEFAULT\s+'([^']+)'", sql)
        assert match, f"{path.name} 未找到 primary_tf 的默认值声明"
        assert match.group(1) == EXPECTED_DEFAULT, f"{path.name} 的 primary_tf 默认值不是 {EXPECTED_DEFAULT}"
