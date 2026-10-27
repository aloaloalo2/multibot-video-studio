"""One font catalog shared by the editor, text layout, and local renderer."""

import json
from pathlib import Path


FONT_ROOT = Path(__file__).resolve().parents[1] / 'frontend' / 'fonts'
CATALOG = json.loads((FONT_ROOT / 'catalog.json').read_text(encoding='utf-8'))
FONT_FILES = {entry['family']: entry for entry in CATALOG}
FONT_FAMILIES = frozenset({'Arial', 'Golos', 'Literata', *FONT_FILES})
FALLBACKS = (
    Path('/System/Library/Fonts/Supplemental/Arial.ttf'),
    Path('/Library/Fonts/Arial Unicode.ttf'),
    Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'),
    Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
)


def font_path(family='Arial', weight=400):
    weight = float(weight or 400)
    if family in FONT_FILES:
        entry = FONT_FILES[family]
        path = FONT_ROOT / entry['bold' if weight >= 550 else 'regular']
        if not path.is_file():
            raise FileNotFoundError(f'Studio font is missing: {path.name}')
        return path
    if family in {'Golos', 'Literata'}:
        return FONT_ROOT / (family.lower() + '.ttf')
    if family == 'Arial' and weight >= 550:
        bold = Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf')
        if bold.is_file():
            return bold
    return next((path for path in FALLBACKS if path.is_file()), None)
