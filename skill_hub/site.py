"""Render a theme folder into the marketplace page, and write the build output safely."""

import os
import shutil
import traceback
from pathlib import Path

import jinja2

from skill_hub.catalog import BuildError
from skill_hub.config import THEME_ENTRY, SiteSettings

INDEX_FILE = "index.html"
CATALOG_FILE = "catalog.json"
MARKER_FILE = ".skill-hub-build"
TEMPLATE_SUFFIX = ".j2"
GENERATED = frozenset({INDEX_FILE, CATALOG_FILE, MARKER_FILE})


def _check_theme(theme_dir: Path) -> None:
    if not theme_dir.is_dir():
        raise BuildError(f"theme folder {theme_dir.name} not found")
    entry = theme_dir / THEME_ENTRY
    if entry.is_symlink() or not entry.is_file():
        raise BuildError(f"theme {theme_dir.name} has no {THEME_ENTRY}")


def _static_files(theme_dir: Path, warnings: list[str]) -> list[Path]:
    """Theme files to copy, relative to theme_dir: templates and dot-entries left out, symlinks skipped."""
    files = []
    for dirpath, dirnames, filenames in os.walk(theme_dir):
        base = Path(dirpath)
        for name in sorted(dirnames):
            if name.startswith(".") or (base / name).is_symlink():
                dirnames.remove(name)
                if not name.startswith("."):
                    rel = (base / name).relative_to(theme_dir).as_posix()
                    warnings.append(f"{theme_dir.name}/{rel}: symlink in theme is not followed")
        dirnames.sort()
        for name in sorted(filenames):
            path = base / name
            rel = path.relative_to(theme_dir).as_posix()
            if name.startswith(".") or name.endswith(TEMPLATE_SUFFIX):
                continue
            if path.is_symlink():
                warnings.append(f"{theme_dir.name}/{rel}: symlink in theme is not followed")
            elif rel in GENERATED:
                raise BuildError(f"theme file {theme_dir.name}/{rel} would overwrite the generated {rel}")
            elif path.is_file():
                files.append(Path(rel))
    return files


def _template_error(exc: jinja2.TemplateError, theme_dir: Path) -> BuildError:
    """A BuildError naming the theme file and line where rendering failed."""
    message = exc.message or type(exc).__name__
    if isinstance(exc, jinja2.TemplateSyntaxError) and exc.name:
        return BuildError(f"{theme_dir.name}/{exc.name}:{exc.lineno}: {message}")
    # Jinja rewrites tracebacks so template frames carry the template's path and line.
    for frame in reversed(traceback.extract_tb(exc.__traceback__)):
        path = Path(frame.filename)
        if path.is_relative_to(theme_dir):
            return BuildError(f"{theme_dir.name}/{path.relative_to(theme_dir).as_posix()}:{frame.lineno}: {message}")
    return BuildError(f"{theme_dir.name}: {message}")


def render_theme(catalog: dict, site: SiteSettings, theme_dir: Path, dest: Path) -> list[str]:
    """Render theme_dir into the existing folder dest and return warnings. Raises BuildError."""
    theme_dir = theme_dir.resolve()
    _check_theme(theme_dir)
    warnings: list[str] = []
    files = _static_files(theme_dir, warnings)
    environment = jinja2.Environment(
        loader=jinja2.FileSystemLoader(theme_dir),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
    )
    context = {"catalog": catalog, "site": {"accent": site.accent, "logo_url": site.logo_url}}
    try:
        html = environment.get_template(THEME_ENTRY).render(context)
    except jinja2.TemplateError as exc:
        raise _template_error(exc, theme_dir) from None
    except (OSError, UnicodeDecodeError):
        raise BuildError(f"theme {theme_dir.name}: a template could not be read as UTF-8 text") from None
    (dest / INDEX_FILE).write_text(html, encoding="utf-8")
    for rel in files:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(theme_dir / rel, target)
    return warnings
