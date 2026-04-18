"""Unit tests for tti.py."""

import pytest
from callevision import tti


SAMPLE_TTI = """\
DE,Test page
DS,callevision
PN,11000
SC,0000
PS,8000
RE,0
OL,1,Hello
"""

SAMPLE_TTI_NO_PN = """\
DE,Test page
OL,1,Hello
"""


class TestValidate:
    def test_valid_pn_first(self):
        assert tti.validate("PN,11000\nOL,1,Hello\n")

    def test_valid_de_header(self):
        assert tti.validate("DE,My page\nPN,11000\n")

    def test_valid_ds_header(self):
        assert tti.validate("DS,callevision\nPN,20000\n")

    def test_valid_full_sample(self):
        assert tti.validate(SAMPLE_TTI)

    def test_invalid_empty(self):
        assert not tti.validate("")

    def test_invalid_json(self):
        assert not tti.validate('{"title": "Weather"}')

    def test_invalid_plain_text(self):
        assert not tti.validate("Hello world\nThis is not TTI\n")

    def test_valid_pn_after_blank_lines(self):
        assert tti.validate("\n\nPN,20000\nOL,1,text\n")


class TestRewritePN:
    def test_no_mismatch(self):
        payload = "PN,11000\nOL,1,Hello\n"
        result, mismatch = tti.rewrite_pn(payload, 110)
        assert not mismatch
        assert "PN,11000\n" in result

    def test_mismatch_detected(self):
        payload = "PN,11000\nOL,1,Hello\n"
        result, mismatch = tti.rewrite_pn(payload, 200)
        assert mismatch
        assert "PN,20000\n" in result
        assert "PN,11000" not in result

    def test_subpage_preserved(self):
        payload = "PN,11001\nOL,1,Hello\n"
        result, mismatch = tti.rewrite_pn(payload, 200)
        assert "PN,20001\n" in result

    def test_no_pn_line_inserts_one(self):
        result, mismatch = tti.rewrite_pn(SAMPLE_TTI_NO_PN, 300)
        assert "PN,30000" in result
        assert not mismatch

    def test_full_sample_rewrite(self):
        result, mismatch = tti.rewrite_pn(SAMPLE_TTI, 110)
        assert not mismatch
        assert "PN,11000\n" in result

    def test_page_format_three_digits(self):
        payload = "PN,89900\nOL,1,x\n"
        result, _ = tti.rewrite_pn(payload, 100)
        assert "PN,10000\n" in result

    def test_other_lines_unchanged(self):
        result, _ = tti.rewrite_pn(SAMPLE_TTI, 110)
        assert "OL,1,Hello\n" in result
        assert "DE,Test page\n" in result
