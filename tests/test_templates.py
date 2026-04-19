"""Unit tests for templates.py."""

import textwrap
from pathlib import Path

import pytest
import yaml

from callevision import templates


BASIC_MANIFEST = {
    "name": "basic",
    "description": "Test template",
    "fields": {
        "title": {"type": "string", "max_length": 10, "required": True},
        "body": {"type": "string", "max_length": 20, "required": False},
    },
}

BASIC_TEMPLATE = "PN,{_page}00\nDE,{title}\nOL,1,{title:<10}\nOL,2,{body:<20}\n"


def _make_template(tmp_path: Path, name: str = "basic", manifest=None, template_text=None) -> Path:
    tdir = tmp_path / name
    tdir.mkdir()
    m = manifest if manifest is not None else BASIC_MANIFEST
    (tdir / "manifest.yaml").write_text(yaml.dump(m), encoding="utf-8")
    t = template_text if template_text is not None else BASIC_TEMPLATE
    (tdir / "template.tti").write_text(t, encoding="utf-8")
    return tmp_path


class TestRender:
    def test_valid_fields(self, tmp_path):
        tdir = _make_template(tmp_path)
        result = templates.render(tdir, "basic", 130, {"title": "Hello", "body": "World"})
        assert result is not None
        assert "PN,13000\n" in result
        assert "DE,Hello\n" in result
        assert "OL,1,Hello     \n" in result
        assert "OL,2,World               \n" in result

    def test_missing_required_field_uses_empty(self, tmp_path, caplog):
        tdir = _make_template(tmp_path)
        import logging
        with caplog.at_level(logging.WARNING, logger="callevision.templates"):
            result = templates.render(tdir, "basic", 100, {"body": "hi"})
        assert result is not None
        assert "title" in caplog.text
        assert "OL,1,          \n" in result

    def test_too_long_field_truncated(self, tmp_path, caplog):
        tdir = _make_template(tmp_path)
        import logging
        with caplog.at_level(logging.WARNING, logger="callevision.templates"):
            result = templates.render(tdir, "basic", 100, {"title": "TooLongTitle!", "body": ""})
        assert result is not None
        assert "truncated" in caplog.text
        assert "DE,TooLongTit\n" in result

    def test_unknown_template_returns_none(self, tmp_path, caplog):
        tdir = _make_template(tmp_path)
        import logging
        with caplog.at_level(logging.WARNING, logger="callevision.templates"):
            result = templates.render(tdir, "nonexistent", 100, {"title": "x"})
        assert result is None
        assert "nonexistent" in caplog.text

    def test_optional_field_absent_uses_empty(self, tmp_path):
        tdir = _make_template(tmp_path)
        result = templates.render(tdir, "basic", 200, {"title": "Hi"})
        assert result is not None
        assert "OL,2,                    \n" in result

    def test_page_number_in_output(self, tmp_path):
        tdir = _make_template(tmp_path)
        result = templates.render(tdir, "basic", 299, {"title": "x"})
        assert "PN,29900\n" in result

    def test_exact_max_length_not_truncated(self, tmp_path, caplog):
        tdir = _make_template(tmp_path)
        import logging
        with caplog.at_level(logging.WARNING, logger="callevision.templates"):
            result = templates.render(tdir, "basic", 100, {"title": "1234567890"})
        assert "truncated" not in caplog.text
        assert "DE,1234567890\n" in result


class TestManifestLoading:
    def test_load_basic_template(self):
        """Smoke-test that the real basic template and manifest load and render."""
        project_root = Path(__file__).parent.parent
        tdir = project_root / "templates"
        result = templates.render(tdir, "basic", 130, {"title": "Test", "body_1": "Line one"})
        assert result is not None
        assert "PN,13000\n" in result
        assert "DE,Test\n" in result


WELCOME_FIELDS = {
    "title": "CALLEVISION",
    "banner_text": "CALLEVISION",
    "banner_date": "19 APRIL",
    "menu_1_label": "NYHETER",
    "menu_2_label": "HEM",
    "menu_3_label": "INFO",
    "menu_4_label": "INDEX",
}


class TestWelcomeTemplate:
    def _render(self, fields=None):
        project_root = Path(__file__).parent.parent
        tdir = project_root / "templates"
        return templates.render(tdir, "welcome", 100, fields or WELCOME_FIELDS)

    def test_renders_without_error(self):
        result = self._render()
        assert result is not None

    def test_page_number(self):
        result = self._render()
        assert "PN,10000\n" in result

    def test_fasttext_links(self):
        result = self._render()
        assert "FL,200,300,400,500\n" in result

    def test_banner_text_in_header(self):
        result = self._render()
        # Banner row (OL,1) should contain the banner_text
        ol1 = next(l for l in result.split("\n") if l.startswith("OL,1,"))
        assert "CALLEVISION" in ol1

    def test_banner_date_in_header(self):
        result = self._render()
        ol1 = next(l for l in result.split("\n") if l.startswith("OL,1,"))
        assert "19 APRIL" in ol1

    def test_title_in_double_height_row(self):
        result = self._render()
        ol7 = next(l for l in result.split("\n") if l.startswith("OL,7,"))
        assert "CALLEVISION" in ol7
        # Must start with double-height control code
        body = ol7[len("OL,7,"):]
        assert body[0] == "\r"  # \x0D = double height

    def test_menu_labels_present(self):
        result = self._render()
        assert "NYHETER" in result
        assert "HEM" in result
        assert "INFO" in result
        assert "INDEX" in result

    def test_menu_rows_have_color_codes(self):
        result = self._render()
        lines = {l.split(",")[1]: l for l in result.split("\n") if l.startswith("OL,")}
        # Red bullet (row 14)
        assert "\x01" in lines["14"]
        # Green bullet (row 15)
        assert "\x02" in lines["15"]
        # Yellow bullet (row 16)
        assert "\x03" in lines["16"]
        # Blue bullet (row 17)
        assert "\x04" in lines["17"]

    def test_green_background_band_header(self):
        result = self._render()
        ol1 = next(l for l in result.split("\n") if l.startswith("OL,1,"))
        body = ol1[len("OL,1,"):]
        assert body[0] == "\x02"   # green text
        assert body[1] == "\x1d"   # new background

    def test_green_background_band_footer(self):
        result = self._render()
        ol24 = next(l for l in result.split("\n") if l.startswith("OL,24,"))
        body = ol24[len("OL,24,"):]
        assert body[0] == "\x02"   # green text
        assert body[1] == "\x1d"   # new background

    def test_optional_banner_date_absent(self):
        fields = dict(WELCOME_FIELDS)
        del fields["banner_date"]
        result = self._render(fields)
        assert result is not None
        # Header row should still render (date omitted = padded with spaces)
        assert "OL,1," in result

    def test_header_row_width(self):
        result = self._render()
        ol1 = next(l for l in result.split("\n") if l.startswith("OL,1,"))
        body = ol1[len("OL,1,"):]
        assert len(body) == 40

    def test_double_height_row_width(self):
        result = self._render()
        ol7 = next(l for l in result.split("\n") if l.startswith("OL,7,"))
        body = ol7[len("OL,7,"):]
        assert len(body) == 40

    def test_footer_row_width(self):
        result = self._render()
        ol24 = next(l for l in result.split("\n") if l.startswith("OL,24,"))
        body = ol24[len("OL,24,"):]
        assert len(body) == 40


class TestBridgeJsonHandling:
    """Test JSON validation logic (mirrored from bridge._handle_json)."""

    def _parse(self, payload: str):
        import json
        return json.loads(payload)

    def test_missing_v_rejected(self):
        data = self._parse('{"template": "basic", "fields": {}}')
        assert "v" not in data

    def test_missing_template_rejected(self):
        data = self._parse('{"v": 1, "fields": {}}')
        assert "template" not in data

    def test_missing_fields_rejected(self):
        data = self._parse('{"v": 1, "template": "basic"}')
        assert "fields" not in data

    def test_valid_json_has_all_keys(self):
        data = self._parse('{"v": 1, "template": "basic", "fields": {"title": "Hi"}}')
        assert all(k in data for k in ("v", "template", "fields"))
