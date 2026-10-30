"""A voice said out of order, or with a piece said twice, is caught after the script comparison and sent to review.

The comparison (speech.compare_script) walks the script and the voice side by side, so a sentence said in another place
reads there only as missing, and a piece said twice is matched once while the second copy is quietly left over. Here
every sentence of the script is looked for in the whole voice: a sentence heard more often than the script has it was
repeated, and one heard away from the order of its neighbours was said out of place. Both stop the timings with a plain
note of where it happened. The voice itself is never cut or moved: the author fixes it (user, 30 October 2026: «лише
ловити, нічого не виправляти, тому що це озвучка і треба, щоб я сам виправляв»).
"""
from __future__ import annotations

from collections import Counter, defaultdict

import number_text
import planner

ORDER_ISSUES = {"out_of_order", "repeated_speech"}
MIN_TOKENS = 5      # shorter sentences («It's called brown fat.») turn up elsewhere by chance
GRAM = 3
SHARE = .6          # share of a sentence's word triples one hearing of it must hold


def clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}" if seconds >= 3600 else f"{seconds // 60}:{seconds % 60:02d}"


def times(count: int) -> str:
    return "двічі" if count == 2 else f"{count} рази" if count < 5 else f"{count} разів"


def hearings(sentence: list[str], index: dict, separation: int) -> list[int]:
    """Where in the voice this sentence was said: positions that many of its word triples point to."""
    grams = [tuple(sentence[k:k + GRAM]) for k in range(len(sentence) - GRAM + 1)]
    votes = Counter()
    for k, gram in enumerate(grams):
        for position in index.get(gram, ()):
            votes[position - k] += 1
    # a word added or dropped on the way shifts the triples by one or two: neighbouring starts count together
    groups, found = [], []
    for start in sorted(votes):
        if groups and start - groups[-1][-1] <= 2:
            groups[-1].append(start)
        else:
            groups.append([start])
    for group in groups:
        if sum(votes[start] for start in group) >= SHARE * len(grams):
            begin = max(0, group[0])
            if not found or begin - found[-1] >= separation:
                found.append(begin)
    return found


def longest_in_order(positions: list[tuple[int, int]]) -> set[int]:
    """Of (sentence number, position) pairs in script order, the sentences that keep their order: the longest run of
    growing positions. The rest were said out of place."""
    chains = []
    for k, (_, position) in enumerate(positions):
        before = [chains[j] for j in range(k) if positions[j][1] < position]
        chains.append(max(before, key=len, default=[]) + [k])
    return {positions[k][0] for k in max(chains, key=len, default=[])}


def triples(tokens: list[str]) -> dict:
    index = defaultdict(list)
    for position in range(len(tokens) - GRAM + 1):
        index[tuple(tokens[position:position + GRAM])].append(position)
    return index


def check(script: str, words: list[dict]) -> dict[int, dict]:
    """Sentence number -> what is wrong with its place in the voice: {"repeated": [seconds, ...]} or {"moved": seconds}."""
    locale = number_text.detect_locale(script)
    heard, owner = [], []
    for k, word in enumerate(words):
        for token in number_text.comparison_tokens(str(word.get("text", "")), locale):
            heard.append(token)
            owner.append(k)
    sentences = [number_text.comparison_tokens(sentence, locale) for sentence in planner.split_sentences(script)]
    index, written = triples(heard), triples([token for tokens in sentences for token in tokens])
    at = lambda position: float(words[owner[position]]["start"])
    found, firsts = {}, []
    for number, tokens in enumerate(sentences, 1):
        if len(tokens) < MIN_TOKENS:
            continue
        separation = max(GRAM, len(tokens) // 2)
        # a script that says the same words again («That brings us to…», a line said once more inside a longer one)
        # expects them as often in the voice: only hearings beyond that are repeats, and only lines said once have a place
        places, expected = hearings(tokens, index, separation), len(hearings(tokens, written, separation))
        if len(places) > expected:
            found[number] = {"repeated": [at(place) for place in places]}
        if places and expected == 1:
            firsts.append((number, places[0]))
    keep = longest_in_order(firsts)
    for number, place in firsts:
        if number not in keep:
            found.setdefault(number, {})["moved"] = at(place)
    return found


def mark(script: str, words: list[dict], report: dict, blocking: set | None = None) -> dict:
    """Put what check() found into the comparison report: issues on the phrases, plain notes, and no timings.
    `blocking` are the comparison's own issues that already keep a phrase from counting as matched (None: any issue)."""
    found = check(script, words)
    if not found:
        return report
    phrases, lost = report.get("phrases") or [], 0
    for phrase in phrases:
        trouble = found.get(phrase.get("number"))
        if trouble:
            before = set(phrase.get("issues") or [])
            lost += not (before if blocking is None else before & set(blocking))
            phrase["issues"] = list(dict.fromkeys(list(phrase.get("issues") or []) + (["repeated_speech"] if "repeated" in trouble else [])
                                                  + (["out_of_order"] if "moved" in trouble else [])))
    notes = []
    for number, trouble in sorted(found.items()):
        if "repeated" in trouble:
            notes.append({"kind": "repeated", "sentences": [number], "expected": "", "recognized": "",
                          "note": f"Фраза {number} прозвучала {times(len(trouble['repeated']))}: " + ", ".join(f"о {clock(t)}" for t in trouble["repeated"]) + "."})
        if "moved" in trouble:
            notes.append({"kind": "moved", "sentences": [number], "expected": "", "recognized": "",
                          "note": f"Фраза {number} прозвучала не на своєму місці, о {clock(trouble['moved'])}."})
    report = {**report, "status": "needs_review", "timings": None, "differences": notes + list(report.get("differences") or [])}
    report["matched_phrases"] = max(0, int(report.get("matched_phrases") or 0) - lost)
    return report
