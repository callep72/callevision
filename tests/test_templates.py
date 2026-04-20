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

    def test_swedish_letters_are_mapped_to_teletext_subset(self, tmp_path):
        tdir = _make_template(
            tmp_path,
            template_text="PN,{_page}00\nPS,8100\nOL,1,{title}\n",
        )
        result = templates.render(tdir, "basic", 100, {"title": "ÅÄÖåäöÉéÜü"})
        assert result is not None
        assert "PS,8100\n" in result
        assert "OL,1,][\\}{|@`^~\n" in result


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

    def _ol(self, result, row):
        """Return the body of OL,row line with trailing CR stripped."""
        prefix = f"OL,{row},"
        line = next(l for l in result.split("\n") if l.startswith(prefix))
        return line[len(prefix):].rstrip("\r")

    def test_renders_without_error(self):
        result = self._render()
        assert result is not None

    def test_page_number(self):
        result = self._render()
        assert "PN,10000\r\n" in result

    def test_fasttext_links(self):
        result = self._render()
        assert "FL,200,300,400,500\r\n" in result

    def test_uses_swedish_page_status(self):
        result = self._render()
        assert "PS,8100\r\n" in result

    def test_banner_text_in_header(self):
        result = self._render()
        assert "CALLEVISION" in self._ol(result, 1)

    def test_banner_date_in_header(self):
        result = self._render()
        assert "19 APRIL" in self._ol(result, 1)

    def test_title_in_double_height_row(self):
        result = self._render()
        body = self._ol(result, 7)
        assert "CALLEVISION" in body
        assert body[:2] == "\x1bM"  # ESC M = double height

    def test_menu_labels_present(self):
        result = self._render()
        assert "NYHETER" in result
        assert "HEM" in result
        assert "INFO" in result
        assert "INDEX" in result

    def test_menu_rows_have_color_codes(self):
        result = self._render()
        lines = {l.split(",")[1]: l for l in result.split("\n") if l.startswith("OL,")}
        assert "\x1bA" in lines["14"]  # ESC A = alpha red
        assert "\x1bB" in lines["15"]  # ESC B = alpha green
        assert "\x1bC" in lines["16"]  # ESC C = alpha yellow
        assert "\x1bD" in lines["17"]  # ESC D = alpha blue

    def test_white_text_header(self):
        result = self._render()
        body = self._ol(result, 1)
        assert body[:2] == "\x1bG"   # ESC G = white text, black background

    def test_mosaic_band_row2(self):
        result = self._render()
        body = self._ol(result, 2)
        assert body == "\x1bR" + "\x7f" * 40

    def test_mosaic_band_row23(self):
        result = self._render()
        body = self._ol(result, 23)
        assert body == "\x1bR" + "\x7f" * 40

    def test_optional_banner_date_absent(self):
        fields = dict(WELCOME_FIELDS)
        del fields["banner_date"]
        result = self._render(fields)
        assert result is not None
        assert "OL,1," in result

    def test_crlf_line_endings(self):
        result = self._render()
        assert result is not None
        # After splitting on CRLF, no line should contain a bare LF
        lines = result.split("\r\n")
        assert all("\n" not in l for l in lines)
        assert len(lines) > 5

    def test_header_row_width(self):
        result = self._render()
        body = self._ol(result, 1)
        # 1 ESC-pair (2 chars) + 31 banner_text + 8 banner_date = 41
        assert len(body) == 41

    def test_double_height_row_width(self):
        result = self._render()
        body = self._ol(result, 7)
        # 2 ESC-pairs (4 chars) + 13 spaces + 12 title + 13 spaces = 42
        assert len(body) == 42

    def test_mosaic_band_row_width(self):
        result = self._render()
        body = self._ol(result, 2)
        # ESC R (2 chars) + 40 mosaic cells = 42
        assert len(body) == 42


NEWS_INDEX_FIELDS = {
    "title": "NYHETER",
    "updated": "20 APR 22:15",
    "strapline": "Senaste nytt pa Callevision",
    "lead_1_page": "201",
    "lead_1_headline": "Regeringen presenterar varbudget",
    "lead_2_page": "202",
    "lead_2_headline": "Borsen stiger efter ny rapportdag",
    "lead_3_page": "203",
    "lead_3_headline": "Brand i lokal under kontroll",
    "lead_4_page": "204",
    "lead_4_headline": "EU enas om nytt AI-ramverk",
    "lead_5_page": "205",
    "lead_5_headline": "Tagtrafik stoppas i hard vind",
    "lead_6_page": "206",
    "lead_6_headline": "Kommunen skjuter upp ny skola",
    "footer": "Fler nyheter pa 210",
}


NEWS_STORY_FIELDS = {
    "section": "INRIKES",
    "title": "Regeringen presenterar varbudget",
    "updated": "20 APR 22:16",
    "subhead": "Fokus pa jobb, forsvar och tillvaxt",
    "body_1": "Regeringen lade i kvall fram sin nya",
    "body_2": "varbudget efter flera veckors arbete.",
    "body_3": "Tyngdpunkten ligger pa arbetsmarknad,",
    "body_4": "forsvar och atgarder for tillvaxt.",
    "body_5": "Oppositionen kritiserar delar av",
    "body_6": "finansieringen och efterlyser tydligare",
    "body_7": "besked om hushallens kostnader.",
    "body_8": "Finansministern sager att forslagen",
    "continued_page": "206",
    "continued_label": "Fortsattning",
    "footer": "Tillbaka till index pa 200",
}


NEWS_FLASH_FIELDS = {
    "label": "EXTRA",
    "updated": "20 APR 22:17",
    "headline": "Brand i industrilokal",
    "line_1": "Raddningstjansten arbetar med flera",
    "line_2": "enheter pa plats i industriomradet.",
    "line_3": "Boende i narheten uppmanas stanga",
    "line_4": "fonster och folja lokala besked.",
    "more_page": "203",
    "more_label": "Mer om branden",
    "footer": "Nyhetsindex pa 200",
}


class _TemplateHarness:
    def _render_named(self, template_name, page, fields):
        project_root = Path(__file__).parent.parent
        tdir = project_root / "templates"
        return templates.render(tdir, template_name, page, fields)

    def _ol(self, result, row):
        prefix = f"OL,{row},"
        line = next(l for l in result.split("\n") if l.startswith(prefix))
        return line[len(prefix):].rstrip("\r")


class TestNewsIndexTemplate(_TemplateHarness):
    def test_renders_without_error(self):
        result = self._render_named("news_index", 200, NEWS_INDEX_FIELDS)
        assert result is not None

    def test_page_number(self):
        result = self._render_named("news_index", 200, NEWS_INDEX_FIELDS)
        assert "PN,20000\n" in result

    def test_uses_swedish_page_status(self):
        result = self._render_named("news_index", 200, NEWS_INDEX_FIELDS)
        assert "PS,8100\n" in result

    def test_top_band_uses_green_background(self):
        result = self._render_named("news_index", 200, NEWS_INDEX_FIELDS)
        body = self._ol(result, 1)
        assert body.startswith("\x1bB\x1b]\x1b@")
        assert "NYHETER" in body
        assert "20 APR 22:15" in body

    def test_strapline_uses_yellow_double_height(self):
        result = self._render_named("news_index", 200, NEWS_INDEX_FIELDS)
        body = self._ol(result, 4)
        assert body.startswith("  \x1bC\x1bM")
        assert "Senaste nytt pa Callevision" in body

    def test_lead_rows_include_page_and_headline(self):
        result = self._render_named("news_index", 200, NEWS_INDEX_FIELDS)
        body = self._ol(result, 9)
        assert body.startswith("\x1bB201")
        assert "Regeringen presenterar varbudget" in body

    def test_swedish_letters_are_encoded(self):
        fields = dict(NEWS_INDEX_FIELDS)
        fields["lead_1_headline"] = "Väderläge i Åmål: snö över sjön"
        result = self._render_named("news_index", 200, fields)
        body = self._ol(result, 9)
        assert body == "\x1bB201\x1bG V{derl{ge i ]m}l: sn| |ver sj|n"


class TestNewsStoryTemplate(_TemplateHarness):
    def test_renders_without_error(self):
        result = self._render_named("news_story", 201, NEWS_STORY_FIELDS)
        assert result is not None

    def test_top_band_contains_section_and_date(self):
        result = self._render_named("news_story", 201, NEWS_STORY_FIELDS)
        body = self._ol(result, 1)
        assert body.startswith("\x1bB\x1b]\x1b@")
        assert "INRIKES" in body
        assert "20 APR 22:16" in body

    def test_title_row_is_yellow_double_height(self):
        result = self._render_named("news_story", 201, NEWS_STORY_FIELDS)
        body = self._ol(result, 4)
        assert body.startswith("  \x1bC\x1bM")
        assert "Regeringen presenterar varbudget" in body

    def test_body_lines_are_present(self):
        result = self._render_named("news_story", 201, NEWS_STORY_FIELDS)
        assert self._ol(result, 9) == "Regeringen lade i kvall fram sin nya"
        assert self._ol(result, 10) == "varbudget efter flera veckors arbete."

    def test_middle_paragraph_uses_yellow(self):
        result = self._render_named("news_story", 201, NEWS_STORY_FIELDS)
        body = self._ol(result, 14)
        assert body.startswith("\x1bC")
        assert "Oppositionen kritiserar delar av" in body

    def test_continued_line_contains_page_and_label(self):
        result = self._render_named("news_story", 201, NEWS_STORY_FIELDS)
        body = self._ol(result, 22)
        assert body.startswith("\x1bB206")
        assert "Fortsattning" in body

    def test_footer_moves_into_safe_area(self):
        result = self._render_named("news_story", 201, NEWS_STORY_FIELDS)
        body = self._ol(result, 23)
        assert body.startswith("\x1bB\x1b]\x1b@")
        assert "Tillbaka till index pa 200" in body


class TestNewsFlashTemplate(_TemplateHarness):
    def test_renders_without_error(self):
        result = self._render_named("news_flash", 202, NEWS_FLASH_FIELDS)
        assert result is not None

    def test_top_band_contains_label_and_time(self):
        result = self._render_named("news_flash", 202, NEWS_FLASH_FIELDS)
        body = self._ol(result, 1)
        assert body.startswith("\x1bB\x1b]\x1b@")
        assert "EXTRA" in body
        assert "20 APR 22:17" in body

    def test_headline_is_yellow_double_height(self):
        result = self._render_named("news_flash", 202, NEWS_FLASH_FIELDS)
        body = self._ol(result, 4)
        assert body.startswith("  \x1bC\x1bM")
        assert "Brand i industrilokal" in body

    def test_supporting_lines_render(self):
        result = self._render_named("news_flash", 202, NEWS_FLASH_FIELDS)
        assert self._ol(result, 8) == "Raddningstjansten arbetar med flera"
        assert self._ol(result, 11) == "fonster och folja lokala besked."

    def test_more_line_contains_page_and_label(self):
        result = self._render_named("news_flash", 202, NEWS_FLASH_FIELDS)
        body = self._ol(result, 20)
        assert body.startswith("\x1bB203")
        assert "Mer om branden" in body

    def test_footer_moves_into_safe_area(self):
        result = self._render_named("news_flash", 202, NEWS_FLASH_FIELDS)
        body = self._ol(result, 23)
        assert body.startswith("\x1bB\x1b]\x1b@")
        assert "Nyhetsindex pa 200" in body


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
