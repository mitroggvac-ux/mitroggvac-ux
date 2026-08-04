import json
from pathlib import Path

import pytest

EXAMPLE_CONFIG = Path(__file__).resolve().parents[1] / "config" / "account.example.json"


@pytest.fixture
def config():
    from pinterest_kit import config as config_module

    raw = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    raw["account"]["handle"] = "test_handle"
    cfg = config_module._with_defaults(raw)
    config_module.validate(cfg)
    return cfg


@pytest.fixture
def ideas():
    return [
        {
            "id": f"idea-{i:02d}",
            "cluster": cluster,
            "hook": f"Заголовок номер {i} про то, что реально пригодится",
            "support": "Короткое пояснение с деталями.",
            "image": f"assets/pins/{i}.jpg",
            "link": "https://example.com/page?ref=abc",
        }
        for i, cluster in enumerate(
            ["beaches", "routes", "food", "seasons", "relocation"] * 4, start=1
        )
    ]
