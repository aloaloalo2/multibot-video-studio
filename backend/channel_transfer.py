"""Portable channel configuration, with bounded ZIP reading and reversible replacement.

Episodes, generated media, service credentials and in-progress jobs never enter the bundle.
Cloud voice IDs remain unchanged and require the same provider account on the receiving Studio.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

import store

MAX_BYTES = 128 * 1024 * 1024
MAX_FILES = 512
FORMAT = 'videokey-channel-settings'
ROOT_FILES = ('competitors.json', 'icon.png', 'logo.png', 'thumbnail-hero.png', 'custom-styles.json', 'portable-rules.json')
VOICE_FILES = ('settings.json', 'reference.mp3', 'reference.json')


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')


def _allowed(name):
    if name in ('settings.json', 'director-memory.json', 'translation-options.json', 'channel-rules.md', 'manifest.json'):
        return True
    parts = PurePosixPath(name).parts
    if len(parts) == 2 and parts[0] == 'channel' and parts[1] in ROOT_FILES:
        return True
    if len(parts) == 2 and parts[0] == 'voice' and (parts[1] in VOICE_FILES or re.fullmatch(r'fish-reference-[0-9a-f]{64}\.(mp3|json)', parts[1])):
        return True
    if len(parts) == 3 and parts[:2] == ('voice', 'prepared') and re.fullmatch(r'[0-9a-f]{64}\.(mp3|json)', parts[2]):
        return True
    if name == 'languages/current.json':
        return True
    if len(parts) == 4 and parts[0] == 'languages' and re.fullmatch(r'[0-9a-f]{32}', parts[1]) and re.fullmatch('[a-z]{2}', parts[2]) and parts[3] in ('own-voice.mp3', 'own-voice.json', 'own-voice.txt'):
        return True
    if len(parts) == 2 and parts[0] == 'style-reference' and Path(parts[1]).suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.txt'):
        return True
    if len(parts) == 2 and parts[0] == 'legacy-voices' and Path(parts[1]).suffix in ('.mp3', '.txt', '.json'):
        return True
    return False


def _has_symlink(path):
    # macOS has a legitimate /var -> /private/var alias above temporary roots.
    # Check the complete managed subtree, without rejecting operating-system aliases.
    roots = {p for base in (store.DATA_ROOT, store.YOUTUBE_ROOT) for p in (base.absolute(), base.resolve())}
    for part in (path, *path.parents):
        if part.is_symlink(): return True
        if part in roots: break
    return False


def _channel_root(cid):
    return store.DATA_ROOT / 'channels' / cid


def _rules(cid, folder):
    import author_rules
    existing = _channel_root(cid) / 'portable-rules.json'
    if existing.is_file():
        result = store.read_json(existing)
    else:
        result = {'author': author_rules.for_channel(folder, store.YOUTUBE_ROOT),
            'director_notes': author_rules.claude_memory(folder.name, limit=30000),
            'shared_rules': author_rules._read(store.YOUTUBE_ROOT / 'AGENTS.md')}
    # This editable list belongs to the receiving Studio, outside a channel ZIP.
    author = dict(result['author'])
    author.pop('studio_word_blacklist', None)
    return {**result, 'author': author}


def export_bundle(cid, *, include_voice_files=False):
    import agent_storage
    folder = store.get_channel_folder(cid)
    files = {}
    mtimes = {}

    def add(name, source):
        if _has_symlink(source):
            raise store.StudioError('У налаштуваннях знайдено символічне посилання. Архів не створено.')
        if source.is_file():
            if len(files) >= MAX_FILES or source.stat().st_size + sum(map(len, files.values())) > MAX_BYTES:
                raise store.StudioError('Налаштування перевищують ліміт архіву 128 МБ.')
            files[name] = source.read_bytes()
            mtimes[name] = source.stat().st_mtime_ns

    add('settings.json', store.channel_settings_source(folder))
    for name in ROOT_FILES:
        add('channel/' + name, _channel_root(cid) / name)
    files['channel/portable-rules.json'] = _json(_rules(cid, folder))
    files['director-memory.json'] = _json({'text': agent_storage.get_memory(cid)})
    add('channel-rules.md', store.channel_rules_source(folder))
    add('translation-options.json', store.DATA_ROOT / 'language-thumbnail-options' / (cid + '.json'))
    voice = _channel_root(cid) / 'voice-lab'
    for name in VOICE_FILES:
        if include_voice_files or name=='settings.json':add('voice/' + name, voice / name)
    if not include_voice_files and 'voice/settings.json' in files:
        import channel_voice_lab
        settings=channel_voice_lab.validated(json.loads(files['voice/settings.json']))
        ids=channel_voice_lab.saved_voice_ids(cid,settings)
        settings.update(heygen_voice_id=ids['heygen'],fish_voice_id=ids['fishaudio'],eleven_voice_id=ids['elevenlabs'])
        if (voice/'reference.mp3').is_file() and not channel_voice_lab.selected_voice_id(settings):
            raise store.StudioError('Спочатку збережіть ID голосу '+settings['provider']+' у налаштуваннях озвучки. Експорт переносить голоси за ID без аудіофайлів',409)
        files['voice/settings.json']=_json(settings)
    for pattern in ('fish-reference-*', 'prepared/*'):
        for file in sorted(voice.glob(pattern)):
            name = 'voice/' + file.relative_to(voice).as_posix()
            if include_voice_files and _allowed(name): add(name, file)
    base = store.DATA_ROOT / 'language-defaults' / cid
    add('languages/current.json', base / 'current.json')
    current = store.read_json(base / 'current.json', {}) or {}
    version = current.get('version', '')
    if current and not include_voice_files:
        current=json.loads(_json(current))
        for code,value in (current.get('payload',{}).get('voices') or {}).items():
            if not value:continue
            if value.get('remote_only'):continue
            meta=store.read_json(base/version/code/'own-voice.json',{}) or {}
            audio=base/version/code/'own-voice.mp3'
            fish_id=meta.get('fish_model') if audio.is_file() and meta.get('fish_stamp')==audio.stat().st_mtime_ns else None
            ids={'elevenlabs':value.get('clone'), 'fishaudio':fish_id}
            if not any(ids.values()):raise store.StudioError('Для голосу перекладу '+code+' ще немає ID. Збережіть голос у сервісі перед експортом',409)
            choices=(current.get('payload',{}).get('language_settings') or {}).get(code) or current.get('payload',{}).get('settings') or {}
            if choices.get('provider') and not ids.get(choices['provider']):raise store.StudioError('Для вибраного сервісу перекладу '+code+' ще немає ID голосу',409)
            current['payload']['voices'][code]={'remote_only':True,'voice_ids':ids,'clone':ids['elevenlabs']}
        import language_defaults
        current['signature']=language_defaults.signature(current['payload'])
        files['languages/current.json']=_json(current)
    if re.fullmatch('[0-9a-f]{32}', version):
        for file in sorted((base / version).glob('*/*')):
            name = 'languages/' + file.relative_to(base).as_posix()
            if include_voice_files and _allowed(name): add(name, file)
    legacy = folder / 'Голоси для перекладу'
    for file in sorted(legacy.glob('*')):
        name = 'legacy-voices/' + file.name
        if include_voice_files and _allowed(name): add(name, file)
    for file in sorted((folder / 'Еталон стилю').glob('*')):
        name = 'style-reference/' + file.name
        if _allowed(name): add(name, file)
    # ElevenLabs caches are account-scoped. Keep only this channel's existing identities.
    owner = (store.read_json(voice / 'reference.json', {}) or {}).get('clone_owner') or cid
    registry = store.read_json(store.DATA_ROOT / 'voice-clones' / 'elevenlabs.json', {}) or {}
    clones = {key: value for key, value in registry.get('voices', {}).items()
              if value.get('channel_id') in {cid, owner}}
    if len(files) > MAX_FILES or sum(map(len, files.values())) > MAX_BYTES:
        raise store.StudioError('Налаштування перевищують ліміт архіву 128 МБ.')
    manifest = {'format': FORMAT, 'version': 1 if include_voice_files else 2, 'channel_name': store.channel_record(folder)['name'],
                'source_id': cid, 'created_at': time.time(), 'elevenlabs_voices': clones,
                'files': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'mtime_ns': mtimes.get(name)} for name, raw in files.items()}}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', _json(manifest))
        for name, raw in files.items(): archive.writestr(name, raw)
    return output.getvalue()


def read_bundle(raw):
    try:
        if not raw or len(raw) > MAX_BYTES: raise ValueError()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            if len(members) > MAX_FILES + 1 or sum(f.file_size for f in members) > MAX_BYTES: raise ValueError()
            files = {}
            for entry in members:
                name = entry.filename
                if (not _allowed(name) or name in files or '\\' in name or name.startswith('/')
                    or any(p in ('', '.', '..') for p in name.split('/')) or entry.flag_bits & 1
                    or stat.S_ISLNK(entry.external_attr >> 16) or entry.is_dir()): raise ValueError()
                files[name] = archive.read(entry)
        if len(files.get('manifest.json', b'')) > 2 * 1024 * 1024: raise ValueError()
        manifest = json.loads(files.pop('manifest.json'))
        if manifest.get('format') != FORMAT or manifest.get('version') not in (1,2): raise ValueError()
        if manifest['version']==2 and any(name.startswith(('voice/','languages/','legacy-voices/')) and name.endswith(('.mp3','.wav','.flac','.m4a','.ogg','.aac')) for name in files):raise ValueError()
        source = manifest.get('source_id')
        if not isinstance(source, str) or not re.fullmatch('[0-9a-f]{16}', source): raise ValueError()
        if not isinstance(manifest.get('channel_name'), str) or len(manifest['channel_name']) > 200: raise ValueError()
        if set(manifest['files']) != set(files): raise ValueError()
        for name, data in files.items():
            spec = manifest['files'][name]
            if hashlib.sha256(data).hexdigest() != spec['sha256']: raise ValueError()
            stamp = spec.get('mtime_ns')
            if stamp is not None and (type(stamp) is not int or not 0 < stamp < 2**63): raise ValueError()
            if name.endswith('.json'):
                if len(data) > 2 * 1024 * 1024: raise ValueError()
                json.loads(data, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        settings = json.loads(files['settings.json'])
        store.validate_settings(settings)
        memory = json.loads(files.get('director-memory.json', b'{}')).get('text', '')
        if not isinstance(memory, str) or len(memory) > 30000: raise ValueError()
        if 'voice/settings.json' in files:
            import channel_voice_lab
            channel_voice_lab.validated(json.loads(files['voice/settings.json']))
        rules = json.loads(files['channel/portable-rules.json'])
        if not isinstance(rules, dict) or not isinstance(rules.get('author'), dict): raise ValueError()
        if set(rules['author']) != {'author_writing_rules', 'youtube_script_rules', 'channel_script_rules', 'claude_memory_notes'}: raise ValueError()
        if any(not isinstance(v, str) for v in rules['author'].values()): raise ValueError()
        if not all(isinstance(rules.get(k, ''), str) for k in ('director_notes', 'shared_rules')): raise ValueError()
        clones = manifest.get('elevenlabs_voices', {})
        if not isinstance(clones, dict): raise ValueError()
        for key, value in clones.items():
            if not re.fullmatch(r'[0-9a-f]{64}:[0-9a-f]{16}:[a-z]{2}:[0-9a-f]{64}', key): raise ValueError()
            account, owner, language, digest = key.split(':')
            if not isinstance(value, dict) or (value.get('account'), value.get('channel_id'), value.get('language'), value.get('audio_sha256')) != (account, owner, language, digest): raise ValueError()
            if not isinstance(value.get('voice_id'), str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', value['voice_id']): raise ValueError()
        if 'languages/current.json' in files:
            current = json.loads(files['languages/current.json'])
            if not re.fullmatch('[0-9a-f]{32}', current.get('version', '')): raise ValueError()
            payload = current['payload']
            for code, voice in payload['voices'].items():
                if not re.fullmatch('[a-z]{2}', code): raise ValueError()
                if voice and voice.get('remote_only'):
                    ids=voice.get('voice_ids',{})
                    if not isinstance(ids,dict) or not any(ids.values()):raise ValueError()
                    for provider,identity in ids.items():
                        if provider not in ('elevenlabs','fishaudio') or (identity is not None and (not isinstance(identity,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}',identity))):raise ValueError()
                elif voice and any(f"languages/{current['version']}/{code}/own-voice.{ext}" not in files for ext in ('mp3', 'txt')): raise ValueError()
        return manifest, files
    except (ValueError, TypeError, KeyError, AttributeError, OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError, RecursionError):
        raise store.StudioError('Оберіть справний ZIP налаштувань VideoKey Studio. Канал не змінено.') from None


def _targets(cid):
    folder = store.get_channel_folder(cid)
    root = _channel_root(cid)
    return {**{'channel/' + name: root / name for name in ROOT_FILES},
            'settings.json': store.channel_settings_path(folder), 'channel-rules.md': root / 'channel-rules.md',
            'director-memory.json': store.DATA_ROOT / 'agent-channel-memory' / (cid + '.json'),
            'translation-options.json': store.DATA_ROOT / 'language-thumbnail-options' / (cid + '.json'),
            'voice': root / 'voice-lab', 'languages': store.DATA_ROOT / 'language-defaults' / cid,
            'legacy-voices': folder / 'Голоси для перекладу', 'style-reference': folder / 'Еталон стилю'}


def import_bundle(cid, raw, check_idle):
    import channel_voice_lab, languages, language_defaults, eleven_voices
    manifest, files = read_bundle(raw)
    # Shared locks keep settings/reference edits out of the transactional replacement.
    with channel_voice_lab.LOCK, language_defaults.LOCK, languages.LOCK, eleven_voices.LOCK, store.LOCK:
        check_idle(cid)
        import technical_files
        technical_files.migrate_channel(store.get_channel_folder(cid))
        targets = _targets(cid)
        for path in targets.values():
            if _has_symlink(path):
                raise store.StudioError('Налаштування містять символічне посилання. Канал не змінено.')
        backups = store.DATA_ROOT / 'channel-settings-backups' / cid / uuid.uuid4().hex
        previous_bundle = export_bundle(cid,include_voice_files=True)
        backups.mkdir(parents=True)
        (backups / 'settings.zip').write_bytes(previous_bundle)
        store.atomic_json(backups / 'backup.json', {'created_at': time.time()})
        with tempfile.TemporaryDirectory(dir=backups, prefix='staged-') as temp:
            stage = Path(temp)
            for name, data in files.items():
                dest = stage / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                stamp = manifest['files'][name].get('mtime_ns')
                if stamp: os.utime(dest, ns=(stamp, stamp))
            # Keep clone ownership stable for account-scoped ElevenLabs reuse on the new computer.
            refpath = stage / 'voice/reference.json'
            if refpath.is_file():
                meta = store.read_json(refpath, {})
                meta['clone_owner'] = meta.get('clone_owner') or manifest['source_id']
                store.atomic_json(refpath, meta)
            current_path = stage / 'languages/current.json'
            if current_path.is_file():
                current = store.read_json(current_path)
                current['channel_id'] = cid
                store.atomic_json(current_path, current)
            registry_path = store.DATA_ROOT / 'voice-clones/elevenlabs.json'
            if _has_symlink(registry_path):
                raise store.StudioError('Сховище голосів недоступне для перенесення.')
            registry = store.read_json(registry_path, {}) or {}
            registry.setdefault('voices', {}).update(manifest.get('elevenlabs_voices', {}))
            if manifest.get('elevenlabs_voices'):
                targets['registry.json'] = registry_path
                store.atomic_json(stage / 'registry.json', registry)
            applied = []
            try:
                for index, (name, dest) in enumerate(targets.items()):
                    old = backups / ('previous-' + str(index))
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if dest.exists(): os.replace(dest, old)
                    applied.append((dest, old))
                    source = stage / name
                    if source.exists(): os.replace(source, dest)
            except Exception:
                for dest, old in reversed(applied):
                    if dest.is_dir(): shutil.rmtree(dest)
                    else: dest.unlink(missing_ok=True)
                    if old.exists(): os.replace(old, dest)
                raise
        return {'channel': store.channel_record(store.get_channel_folder(cid)), 'imported_from': manifest['channel_name'],
                'backup_id': backups.name}


def backup_path(cid, bid):
    store.get_channel_folder(cid)
    if not isinstance(bid, str) or not re.fullmatch('[0-9a-f]{32}', bid):
        raise store.StudioError('Копію не знайдено', 404)
    path = store.DATA_ROOT / 'channel-settings-backups' / cid / bid
    if not path.is_dir() or _has_symlink(path):
        raise store.StudioError('Копію не знайдено', 404)
    return path


def list_backups(cid):
    store.get_channel_folder(cid)
    root = store.DATA_ROOT / 'channel-settings-backups' / cid
    result = []
    with store.LOCK:
        for path in root.glob('*'):
            if not re.fullmatch('[0-9a-f]{32}', path.name) or path.is_symlink(): continue
            meta = store.read_json(path / 'backup.json', {})
            if not meta: continue
            size = sum(f.stat().st_size for f in path.rglob('*') if f.is_file() and not f.is_symlink())
            result.append({'id': path.name, 'created_at': meta['created_at'], 'bytes': size})
    return sorted(result, key=lambda item: item['created_at'], reverse=True)


def restore_backup(cid, bid, check_idle):
    with store.LOCK:
        raw = (backup_path(cid, bid) / 'settings.zip').read_bytes()
    return import_bundle(cid, raw, check_idle)


def delete_backup(cid, bid):
    with store.LOCK:
        path = backup_path(cid, bid)
        shutil.rmtree(path)
    return {'deleted': True}
