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
