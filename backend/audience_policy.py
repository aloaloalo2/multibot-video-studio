"""Current Studio-wide editorial audience rules, loaded at each new writing step."""
import json
from pathlib import Path

PATH = Path(__file__).resolve().parent / 'resources/audience_policy.json'


def text(stage='writer'):
    value = json.loads(PATH.read_text(encoding='utf-8'))[stage]
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Правило аудиторії Studio відсутнє або пошкоджене.')
    return value.strip()
