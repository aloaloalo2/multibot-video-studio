"""Cheap novelty gates for proposal families, alongside the model's semantic comparison."""
import re
from difflib import SequenceMatcher


def identity(value):
    return re.sub(r'\W', '', value.casefold()) if isinstance(value, str) else ''


def words(value):
    return re.findall(r'[^\W\d_]+|\d+', value.casefold()) if isinstance(value, str) else []


def slot_rewrite(title, previous):
    """Reject near-identical sentence scaffolds with one or two replaced content slots.

    This catches noun, duration and number substitutions. It is deliberately narrower
    than semantic novelty, which the same generation request checks using premises.
    """
    a, b = words(title), words(previous)
    if min(len(a), len(b)) < 6:
        return False
    common = sum(block.size for block in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
    changed = max(len(a), len(b)) - common
    return common / max(len(a), len(b)) >= .8 and changed <= 2


def repeated_premise(premise, previous):
    key = identity(premise)
    if not key:
        return False
    return any(key == identity(old) or slot_rewrite(premise, old) for old in previous if old)
