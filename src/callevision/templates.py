"""Template loading, validation, and rendering."""

import logging
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("callevision.templates")


def _load_manifest(template_dir: Path) -> dict[str, Any]:
    with open(template_dir / "manifest.yaml") as f:
        return yaml.safe_load(f)


def _load_template_text(template_dir: Path) -> str:
    # newline="" preserves CR bytes (used as teletext double-height code \x0D)
    with open(template_dir / "template.tti", encoding="utf-8", newline="") as f:
        return f.read()


def render(templates_dir: Path, template_name: str, page: int, fields: dict[str, str]) -> str | None:
    """Render a named template with the given fields. Returns TTI string or None on failure."""
    template_dir = templates_dir / template_name
    if not template_dir.is_dir():
        log.warning("Template '%s' not found in %s", template_name, templates_dir)
        return None

    manifest = _load_manifest(template_dir)
    template_text = _load_template_text(template_dir)

    render_fields: dict[str, str] = {"_page": str(page)}

    for field_name, spec in manifest.get("fields", {}).items():
        value = fields.get(field_name, "")
        required = spec.get("required", False)
        max_length = spec.get("max_length")

        if required and not value:
            log.warning("Required field '%s' missing for template '%s', using empty string", field_name, template_name)

        if max_length and len(value) > max_length:
            log.warning("Field '%s' truncated from %d to %d chars", field_name, len(value), max_length)
            value = value[:max_length]

        render_fields[field_name] = value

    return template_text.format(**render_fields)
