"""Тесты семантики и текстов пина."""

from pinterest_kit.copywriter import Copywriter
from pinterest_kit.keywords import KeywordBank, keyword_density, normalize, stable_index


def test_normalize_collapses_case_punctuation_and_yo():
    assert normalize("  Пляжи Кипра, без толпы!  ") == "пляжи кипра без толпы"
    assert normalize("Ёлка") == normalize("Елка")


def test_stable_index_is_deterministic():
    assert stable_index("idea-01", 7) == stable_index("idea-01", 7)
    assert 0 <= stable_index("idea-01", 7) < 7


def test_pick_rotates_terms_without_immediate_repeats(config):
    bank = KeywordBank.from_config(config)
    picked = bank.pick("beaches", 4)
    assert len(picked) == 4
    assert len(set(picked)) == 4


def test_pick_with_same_seed_returns_same_terms(config):
    first = KeywordBank.from_config(config).pick("routes", 2, seed="idea-07")
    second = KeywordBank.from_config(config).pick("routes", 2, seed="idea-07")
    assert first == second


def test_coverage_flags_unused_clusters(config):
    bank = KeywordBank.from_config(config)
    coverage = bank.coverage(["beaches", "beaches", "food"])
    assert coverage["beaches"]["pins"] == 2
    assert coverage["routes"]["status"] == "не используется"
    assert coverage["food"]["status"] == "ок"


def test_keyword_density_counts_multiword_terms():
    text = "пляжи кипра и снова пляжи кипра рядом с домом"
    assert keyword_density(text, "пляжи кипра") > 0.4
    assert keyword_density(text, "горы троодос") == 0.0


def test_copy_respects_pinterest_limits(config, ideas):
    writer = Copywriter(config)
    for idea in ideas:
        copy = writer.build(idea)
        assert len(copy.title) <= config["copy"]["title_max"]
        assert len(copy.description) <= config["copy"]["description_max"]
        assert len(copy.alt_text) <= config["copy"]["alt_max"]


def test_copy_puts_keyword_into_title_and_description(config, ideas):
    writer = Copywriter(config)
    copy = writer.build(ideas[0])
    assert normalize(copy.term) in normalize(copy.description)
    assert "в заголовке нет ключа" not in " ".join(copy.warnings)


def test_copy_is_deterministic_for_same_item(config, ideas):
    first = Copywriter(config).build(ideas[3])
    second = Copywriter(config).build(ideas[3])
    assert first.to_dict() == second.to_dict()


def test_utm_added_without_dropping_existing_params(config, ideas):
    copy = Copywriter(config).build(ideas[0])
    assert "ref=abc" in copy.link
    assert "utm_source=pinterest" in copy.link


def test_utm_disabled_leaves_link_untouched(config, ideas):
    config["utm"]["enabled"] = False
    copy = Copywriter(config).build(ideas[0])
    assert copy.link == ideas[0]["link"]


def test_existing_utm_is_not_overwritten(config):
    writer = Copywriter(config)
    link = writer.build_link("https://example.com/x?utm_source=newsletter")
    assert "utm_source=newsletter" in link
    assert "utm_source=pinterest" not in link


def test_single_keyword_occurrence_is_not_stuffing(config, ideas):
    """Одно вхождение ключа — это цель, а не нарушение: предупреждать не о чем."""
    writer = Copywriter(config)
    for idea in ideas:
        copy = writer.build(idea)
        assert not any("переспам" in w for w in copy.warnings), copy.description


def test_term_occurrences_counts_whole_term():
    from pinterest_kit.keywords import term_occurrences

    assert term_occurrences("пляжи кипра и пляжи кипра", "пляжи кипра") == 2
    assert term_occurrences("пляжи кипра", "горы") == 0


def test_warnings_catch_stuffing_and_caps(config):
    config["copy"]["title_templates"] = ["{term} {term} {term}"]
    config["copy"]["description_templates"] = ["{term} {term} {term} {term}"]
    copy = Copywriter(config).build(
        {"id": "x1", "cluster": "beaches", "hook": "hook", "support": ""}
    )
    joined = " ".join(copy.warnings)
    assert "переспам" in joined
    assert "описание короче" in joined


def test_unknown_template_field_raises_readable_error(config):
    config["copy"]["title_templates"] = ["{unknown_field}"]
    writer = Copywriter(config)
    try:
        writer.build({"id": "x", "cluster": "food", "hook": "h"})
    except KeyError as exc:
        assert "unknown_field" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("ожидалась KeyError с подсказкой")
