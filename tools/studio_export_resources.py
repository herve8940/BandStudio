"""Files shared by the macOS, Windows and code-only concert export packages."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def export_resources():
    studio = ROOT / 'desktop/studio'
    for name in ('passage_edit.py', 'live_set.py', 'show_export.py', 'show_control.py'):
        yield studio / name, name
    for path in sorted((studio / 'export_assets').iterdir()):
        name = path.name + '.txt' if path.suffix == '.xml' else path.name
        yield path, 'tools/show_assets/' + name
    for name in ('__init__.py', 'lighting.py', 'i18n.py'):
        yield ROOT / 'reacue_mcp' / name, 'tools/reacue_mcp/' + name
