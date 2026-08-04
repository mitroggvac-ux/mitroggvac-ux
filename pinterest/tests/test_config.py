import pytest

from pinterest_kit import config as config_module


def test_example_config_is_valid(config):
    assert config["account"]["handle"] == "test_handle"
    assert config["cadence"]["pins_per_day"] <= len(config["cadence"]["slots"])


def test_missing_handle_and_niche_reported_together():
    raw = config_module._with_defaults({"boards": [], "clusters": {}})
    with pytest.raises(config_module.ConfigError) as exc:
        config_module.validate(raw)
    message = str(exc.value)
    assert "account.handle" in message
    assert "account.niche" in message
    assert "boards" in message


def test_board_name_length_limit(config):
    config["boards"][0]["name"] = "x" * (config_module.BOARD_NAME_MAX + 1)
    with pytest.raises(config_module.ConfigError, match="name длиннее"):
        config_module.validate(config)


def test_duplicate_board_keys_rejected(config):
    config["boards"][1]["key"] = config["boards"][0]["key"]
    with pytest.raises(config_module.ConfigError, match="дублируется"):
        config_module.validate(config)


def test_board_referencing_unknown_cluster_rejected(config):
    config["boards"][0]["clusters"] = ["no-such-cluster"]
    with pytest.raises(config_module.ConfigError, match="не описан в clusters"):
        config_module.validate(config)


def test_slots_must_cover_daily_volume(config):
    config["cadence"]["pins_per_day"] = len(config["cadence"]["slots"]) + 1
    with pytest.raises(config_module.ConfigError, match="слотов меньше"):
        config_module.validate(config)


def test_bad_slot_format_rejected(config):
    config["cadence"]["slots"].append("25:00")
    with pytest.raises(config_module.ConfigError, match="HH:MM"):
        config_module.validate(config)


def test_title_limit_cannot_exceed_pinterest_max(config):
    config["copy"]["title_max"] = config_module.PIN_TITLE_MAX + 10
    with pytest.raises(config_module.ConfigError, match="title_max"):
        config_module.validate(config)


def test_load_missing_file_gives_actionable_message(tmp_path):
    with pytest.raises(config_module.ConfigError, match="account.example.json"):
        config_module.load(tmp_path / "nope.json")
