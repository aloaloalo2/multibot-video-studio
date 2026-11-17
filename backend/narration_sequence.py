"""Prove the order of Studio-generated takes without trusting ASR spelling."""
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
from fractions import Fraction

import number_text
import planner
import store
import job_timing


def sentence_timings(root, baseline, rows, ending, job, base_hash):
    """Measure take boundaries in the exact MP3 assembly, including codec padding."""
    speech_seconds = ending.get('speech_duration')
    if type(speech_seconds) not in (int, float) or not math.isfinite(speech_seconds) or speech_seconds <= 0:
        return None
    entries = 'stream=time_base,sample_rate:packet=duration:packet_tags:packet_side_data'

    def probe(source, concat=False):
        command = ['ffprobe', '-v', 'error']
        if concat:
            command += ['-f', 'concat', '-safe', '0', '-segment_time_metadata', '1']
        run = subprocess.run(command + ['-i', str(source), '-select_streams', 'a:0', '-show_packets',
                             '-show_streams', '-show_entries', entries, '-of', 'json'], capture_output=True, timeout=90)
        if run.returncode:
            raise ValueError('Cannot measure the saved audio assembly')
        return json.loads(run.stdout)

    try:
        source, joined = probe(root / 'concat.txt', True), probe(baseline)
        stream, base_stream = source['streams'][0], joined['streams'][0]
        if stream['sample_rate'] != base_stream['sample_rate'] or stream['time_base'] != base_stream['time_base']:
            return None
        packets, base_packets = source['packets'], joined['packets']
        groups, ticks = [], 0
        for packet in packets:
            marker = packet['tags'].get('lavf.concatdec.start_time', packet['tags'].get('lavf.concat.start_time'))
            if marker is None:
                return None
            if not groups or groups[-1][0] != marker:
                groups.append((marker, ticks))
            if type(packet['duration']) is not int or packet['duration'] <= 0:
                return None
            ticks += packet['duration']
        if len(groups) != len(rows) or len(packets) != len(base_packets) or ticks != sum(p['duration'] for p in base_packets):
            return None
        trims = lambda packet, field: sum(s.get(field, 0) for s in packet.get('side_data_list', []) if s.get('side_data_type') == 'Skip Samples')
        rate, tick = int(base_stream['sample_rate']), Fraction(base_stream['time_base'])
        lead = Fraction(trims(base_packets[0], 'skip_samples'), rate)
        tail = Fraction(trims(base_packets[-1], 'discard_padding'), rate)
        ratio = 1. if ending.get('source_sha256') == base_hash else job['speed'] / store.read_json(root / 'speed-original.json')['speed']
        decoded_seconds = float(ticks * tick - lead - tail) / ratio
        if abs(decoded_seconds - speech_seconds) > .15:
            return None
        points = [round(max(0., min(speech_seconds, float(start * tick - lead) / ratio)), 6) for _, start in groups]
        points[0] = 0.
        points.append(speech_seconds)
        if any(end <= start for start, end in zip(points, points[1:])):
            return None
        return [{'start': start, 'end': end} for start, end in zip(points, points[1:])]
    except (OSError, ValueError, TypeError, KeyError, IndexError, ZeroDivisionError, subprocess.SubprocessError):
        return None


def tempo_verified(root, job, baseline, base_hash, source_hash):
    metadata = store.read_json(root / 'speed-original.json', {}) or {}
    if not isinstance(metadata, dict):
        return False
    identity = {'baseline_sha256': base_hash, 'source_sha256': source_hash,
                'speed': job.get('speed'), 'baseline_speed': metadata.get('speed')}
    if 'tempo_derivation' in job:
        derivation = job['tempo_derivation']
        return isinstance(derivation, dict) and all(derivation.get(key) == value for key, value in identity.items())
    # Older speed changes predate the derivation receipt. Rebuild their exact local
    # transform once; names and duration alone cannot establish this relationship.
    speeds = (identity['speed'], identity['baseline_speed'])
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0 for value in speeds):
        return False
    ratio = speeds[0] / speeds[1]
    if not .5 <= ratio <= 2:
        return False
    receipt = root / 'tempo-verification.json'
    expected = {'version': 1, **identity}
    if store.read_json(receipt, {}) == expected:
        return True
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / 'paced.mp3'
        run = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(baseline),
                              '-af', f'atempo={ratio:.6f}', '-b:a', '128k', str(output)],
                             capture_output=True, timeout=600)
        if run.returncode or store.audio_fingerprint(output) != source_hash:
            return False
    store.atomic_json(receipt, expected)
    return True


def take_sentences(rows):
    """How many sentences of the script each saved take reads (1 for takes made before groups), or None when the rows
    cannot prove an order: not a list, a broken row, or a part of a sentence cut for its length."""
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        return None
    counts = [row.get('sentences', 1) for row in rows]
    if any(type(count) is not int or count < 1 for count in counts):
        return None
    return counts


@job_timing.measure('verification')
def verify(project, asset, script):
    """Only an unchanged generated asset and an exact reconstruction qualify.

    Measured take boundaries also establish the sentence timeline independently
    of the spelling or boundaries proposed by speech recognition.
    """
    if not isinstance(script, str) or not script.strip():
        return None
    root = store.project_dir(project['id']) / 'narration'
    try:
        job = store.read_json(root / 'job.json', {}) or {}
        if job.get('status') != 'done':
            # the narration hands on to the recognition before it writes «done» (it keeps the episode reserved until
            # the next stage is registered): wait for it to finish rather than lose the takes' proof
            import time
            import project_narration
            until = time.monotonic() + 30
            while project['id'] in project_narration.ACTIVE and time.monotonic() < until:
                time.sleep(.2)
            job = store.read_json(root / 'job.json', {}) or {}
        if not isinstance(job, dict) or job.get('status') != 'done' or job.get('asset_id') != asset.get('id'):
            return None
        locale = number_text.detect_locale(script)
        if number_text.comparison_tokens(script, locale) != number_text.comparison_tokens(job.get('script', ''), locale):
            return None
        revision=job.get('revision_id')
        if revision:
            if not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}',str(revision)):return None
            revised=store.read_json(root/'revisions'/revision/'proof.json',{}) or {}
            count=len(planner.split_sentences(job['script']))
            if (revised.get('source')=='revised_takes' and revised.get('revision_id')==revision
                    and revised.get('audio_sha256')==store.audio_fingerprint(Path(asset['path']))
                    and revised.get('script_sha256')==hashlib.sha256(job['script'].encode()).hexdigest()
                    and (len(revised.get('sentence_timings') or [])==count
                         or len(revised.get('take_timings') or [])==len(revised.get('take_sentences') or [None])
                         and sum(revised.get('take_sentences') or [])==count)):
                return revised
            return None
        rows = store.read_json(root / 'phrases.json', [])
        sentences = planner.split_sentences(job['script'])
        supplied = planner.split_sentences(script)
        counts = take_sentences(rows)
        if not counts or sum(counts) != len(sentences) or len(sentences) != len(supplied):
            return None
        offset = 0
        for row, count in zip(rows, counts):
            said = ' '.join(sentences[offset:offset + count])
            current = ' '.join(supplied[offset:offset + count])
            offset += count
            if (not re.fullmatch(r'[0-9a-f]{64}', row.get('key', ''))
                    or number_text.comparison_tokens(row.get('text', ''), locale) != number_text.comparison_tokens(said, locale)
                    or number_text.comparison_tokens(current, locale) != number_text.comparison_tokens(said, locale)):
                return None
        listing = '\n'.join("file '" + row['key'] + ".mp3'" for row in rows)
        if (root / 'concat.txt').read_text().strip() != listing:
            return None
        ending = asset.get('narration_ending') or {}
        if not isinstance(ending, dict):
            return None
        baseline = root / 'speed-original.mp3'
        audio_hash = store.audio_fingerprint(Path(asset['path']))
        base_hash = store.audio_fingerprint(baseline)
        if ending.get('sha256') != audio_hash:
            return None
        if ending.get('source_sha256') != base_hash:
            if not tempo_verified(root, job, baseline, base_hash, ending.get('source_sha256')):
                return None
        parts = [store.audio_fingerprint(root / (row['key'] + '.mp3')) for row in rows]
        signature = hashlib.sha256(json.dumps([audio_hash, base_hash, listing, parts, ending.get('speech_duration'),
                                               ending.get('source_sha256'), job.get('speed')]).encode()).hexdigest()
        receipt = root / 'assembly-verification.json'
        cached = store.read_json(receipt, {}) or {}
        if (isinstance(cached, dict) and cached.get('signature') == signature
                and (cached.get('version') == 2 or cached.get('version') == 1 and not ending.get('speech_duration'))):
            return cached
        with tempfile.TemporaryDirectory() as tmp:
            rebuilt = Path(tmp) / 'joined.mp3'
            run = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-f', 'concat', '-safe', '0',
                                  '-i', str(root / 'concat.txt'), '-c', 'copy', str(rebuilt)],
                                 capture_output=True, timeout=180)
            if run.returncode or store.audio_fingerprint(rebuilt) != base_hash:
                return None
        result = {'version': 1, 'signature': signature, 'source': 'generated_takes',
                  'sentences': len(rows), 'audio_sha256': audio_hash, 'assembly_sha256': base_hash}
        measured = sentence_timings(root, baseline, rows, ending, job, base_hash)
        if measured and all(count == 1 for count in counts):
            result.update(version=2, sentence_timings=measured)
        elif measured:
            # takes of several sentences (HeyGen reads a few at once): the takes' edges are measured, the sentences
            # inside a take are placed by the recognition in align
            result.update(version=2, take_timings=measured, take_sentences=counts)
        store.atomic_json(receipt, result)
        return result
    except (OSError, ValueError, TypeError, KeyError, store.StudioError, subprocess.SubprocessError):
        return None


def inside_takes(sentences, takes, counts, words):
    """Sentence spans from takes that read several sentences: a take's edges are measured in the assembly, and inside
    it the recognition finds where one sentence ends and the next begins, halfway through the pause between them. None
    when a boundary inside a take cannot be found: then the whole voice is compared as an uploaded file is."""
    import speech
    if not takes or not counts or len(takes) != len(counts) or sum(counts) != len(sentences):
        return None
    spans, offset = [], 0
    for span, count in zip(takes, counts):
        lo, hi = span['start'], span['end']
        group = sentences[offset:offset + count]
        offset += count
        if count == 1:
            spans.append({'start': lo, 'end': hi})
            continue
        heard = [{**w, 'start': max(0., w['start'] - lo), 'end': min(hi - lo, w['end'] - lo)}
                 for w in words if lo <= (w['start'] + w['end']) / 2 < hi]
        try:
            phrases = speech.compare_script(' '.join(group), heard, hi - lo, sequence_verified=True)['phrases']
        except (ValueError, TypeError, KeyError):
            return None
        if len(phrases) != count:
            return None
        edges = [lo]
        for before, after in zip(phrases, phrases[1:]):
            end, start = before.get('end'), after.get('start')
            if end is None or start is None or start < end - .05:
                return None
            edge = lo + (end + max(end, start)) / 2
            if not edges[-1] < edge < hi:
                return None
            edges.append(round(edge, 6))
        edges.append(hi)
        spans.extend({'start': a, 'end': b} for a, b in zip(edges, edges[1:]))
    return spans


@job_timing.measure('verification')
def align(script, words, duration, proof):
    """Use proven take order/times; recognition refines only words inside each take."""
    import speech
    sentences = planner.split_sentences(script)
    if (proof or {}).get('version') != 2:
        return None
    measured = proof.get('sentence_timings') or inside_takes(sentences, proof.get('take_timings'), proof.get('take_sentences'), words)
    if not measured or len(measured) != len(sentences):
        return None
    timings = [{'text': text, **span} for text, span in zip(sentences, measured)]
    try:
        planner.validate_sentence_timings(script, timings, duration)
    except (ValueError, TypeError, KeyError):
        return None
    phrases, aligned, differences, matched, total, recognized = [], [], [], 0, 0, 0
    for number, (sentence, span) in enumerate(zip(sentences, measured), 1):
        lo, hi = span['start'], span['end']
        heard = [{**w, 'start': max(0., w['start'] - lo), 'end': min(hi - lo, w['end'] - lo)}
                 for w in words if lo <= (w['start'] + w['end']) / 2 < hi]
        report = speech.compare_script(sentence, heard, hi - lo, sequence_verified=True)
        phrase = report['phrases'][0]
        original_issues = phrase['issues']
        phrase.update(number=number, start=lo, end=hi, timing_source='generated_takes', recognition_issues=original_issues,
                      issues=[issue for issue in original_issues if issue not in speech.BLOCKING_ISSUES | {'out_of_order', 'repeated_speech'}])
        phrases.append(phrase)
        matched += report['matched_words'];total += report['script_words'];recognized += report['recognized_words']
        differences.extend({**item, 'sentences': [number]} for item in report['differences'])
        chunks = sentence.split()
        observed = {w['word_index']: w for w in report['aligned_words']}
        points = {len(chunks): hi}
        previous = lo - .000001
        for index in range(len(chunks)):
            start = lo + observed[index]['start'] if index in observed else None
            if start is not None and math.isfinite(start) and previous < start < hi:
                points[index] = start;previous = start
        observed_starts = set(points)
        points.setdefault(0, lo)
        anchors = sorted(points)
        for left, right in zip(anchors, anchors[1:]):
            weights = [max(1, len(word)) for word in chunks[left:right]]
            elapsed, full = 0, sum(weights)
            for index in range(left + 1, right):
                elapsed += weights[index - left - 1]
                points[index] = points[left] + (points[right] - points[left]) * elapsed / full
        for index, text in enumerate(chunks):
            start, end = points[index], points[index + 1]
            if index in observed and start < lo + observed[index]['end'] <= end:
                end = lo + observed[index]['end']
            aligned.append({'text': text, 'sentence': number, 'start': round(start, 6), 'end': round(end, 6),
                            'estimated': index not in observed_starts or observed[index].get('estimated', False)})
    return {'status': 'matched', 'timing_source': 'generated_takes', 'sequence_verification': proof,
            'matched_words': matched, 'script_words': total, 'recognized_words': recognized,
            'word_match_percent': round(matched / total * 100, 1) if total else 0,
            'minimum_phrase_match_percent': speech.MIN_PHRASE_MATCH_PERCENT, 'corrected_words': total - matched,
            'matched_phrases': len(phrases), 'phrase_count': len(phrases), 'phrases': phrases,
            'differences': differences, 'timings': {'duration': duration, 'sentences': timings}, 'aligned_words': aligned}
