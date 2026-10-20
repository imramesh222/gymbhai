"""Our WhatsApp templates keep to what Meta approves (PLAN.md §19.3)."""

import re

import pytest

from app.core import whatsapp_templates as wt
from app.core.config import settings

PLACEHOLDER = re.compile(r"\{(\w+)\}")


@pytest.mark.parametrize("template", list(wt.TEMPLATES.values()), ids=str)
def test_each_template_has_both_languages_with_the_same_variables(template) -> None:
    assert set(template.text) == set(wt.LANGUAGES)
    assert set(template.variables("en")) == set(template.variables("ne"))
    if template.button:
        assert set(template.button.label) == set(wt.LANGUAGES)
        for label in template.button.label.values():
            assert 0 < len(label) <= 25  # Meta's limit for a button's text


@pytest.mark.parametrize("template", list(wt.TEMPLATES.values()), ids=str)
@pytest.mark.parametrize("language", wt.LANGUAGES)
def test_meta_rules(template, language) -> None:
    text = template.text[language]
    # No variable at the very start or end of the body.
    assert not text.startswith("{")
    assert not re.search(r"\{\w+\}\W*$", text), "ends with a variable"
    # Never two side by side.
    assert not re.search(r"\}\s*\{", text)
    assert "\n" not in text and len(text) <= 1024
    # Meta reads {{1}}, {{2}}… numbered in order of first appearance.
    body = template.meta_body(language)
    numbers = [int(n) for n in re.findall(r"\{\{(\d+)\}\}", body)]
    assert sorted(set(numbers)) == list(range(1, len(template.variables(language)) + 1))
    assert not PLACEHOLDER.search(re.sub(r"\{\{\d+\}\}", "", body))
    assert template.name.startswith("gymbhai_")
    assert re.fullmatch(r"[a-z0-9_]{1,512}", template.name)
    assert template.category == "UTILITY"


def test_values_are_one_line_and_never_empty() -> None:
    assert wt.clean("too\nmany\t lines     here") == "too many lines here"
    assert wt.clean("") == "-"
    assert wt.clean(None) == "-"
    assert len(wt.clean("x" * 1000)) == wt.MAX_VALUE


def test_render_and_values_follow_each_languages_order() -> None:
    template = wt.TEMPLATES["money_owed"]
    values = {
        "name": "Sita",
        "gym": "Fitness Zone",
        "amount": "1,500",
        "plan": "1 month",
    }
    assert template.render("en", values) == (
        "Hi Sita, this is Fitness Zone. Rs 1,500 is still to pay for your 1 month "
        "membership. You can pay at the desk or in the app."
    )
    # Nepali puts the plan before the amount: its {{3}} is the plan.
    assert template.values("ne", values) == ["Sita", "Fitness Zone", "1 month", "1,500"]
    assert template.values("en", values) == ["Sita", "Fitness Zone", "1,500", "1 month"]


def test_which_automations_go_by_whatsapp() -> None:
    assert wt.for_rule("expiry", -7).key == "membership_ends"
    assert wt.for_rule("expiry", 0).key == "membership_ends"
    assert wt.for_rule("expiry", 3).key == "membership_ended"
    assert wt.for_rule("dues", 7).key == "money_owed"
    assert wt.for_rule("pt_ending", -3).key == "training_ends"
    assert wt.for_rule("pt_ending", 1).key == "training_ended"
    assert wt.for_rule("pt_dues", 7).key == "training_owed"
    # Marketing, in Meta's terms: push, then SMS.
    for trigger in ("lapsed", "not_visiting", "birthday", "progress"):
        assert wt.for_rule(trigger, 0) is None


def test_nepali_goes_under_the_configured_code(monkeypatch) -> None:
    assert wt.meta_language("en") == ("en", "en")
    monkeypatch.setattr(settings, "whatsapp_nepali_language", "hi")
    assert wt.meta_language("ne") == ("ne", "hi")
    monkeypatch.setattr(settings, "whatsapp_nepali_language", "")
    assert wt.meta_language("ne") == ("en", "en")


def test_button_links_start_where_the_app_and_receipts_are(monkeypatch) -> None:
    monkeypatch.setattr(settings, "public_app_url", "https://app.gymbhai.com/")
    assert wt.OPEN_APP.url() == "https://app.gymbhai.com/"
    assert wt.TEMPLATES["receipt"].button.url() == (
        "https://app.gymbhai.com/api/v1/receipts/"
    )


def test_what_meta_is_sent_for_review() -> None:
    """scripts/whatsapp_templates.py: every variable has an example, and the
    button's link is the template's base and one variable."""
    from scripts import whatsapp_templates as script

    rows = script.all_payloads()
    assert {row["name"] for row in rows} == {t.name for t in wt.TEMPLATES.values()}
    for row in rows:
        body = row["components"][0]
        count = len(re.findall(r"\{\{\d+\}\}", body["text"]))
        assert len(body["example"]["body_text"][0]) == count
        if len(row["components"]) > 1:
            (button,) = row["components"][1]["buttons"]
            assert button["url"].endswith("/{{1}}")
            assert button["example"][0].startswith(button["url"][: -len("{{1}}")])
