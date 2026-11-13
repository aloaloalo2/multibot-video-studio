"""Channel settings, identity, voice and portability HTTP endpoints."""
import re
from pathlib import Path

import agent_storage
import channel_branding
import channel_competitors
import channel_hero
import channel_transfer
import channel_voice_lab
import channel_translation_voices
import json
import languages
import store
import style_copy
import style_lab


def get(self, path, query, *, ensure_idle):
    sample=re.fullmatch(r'/api/channels/([0-9a-f]{16})/voices/([a-z]{2})/sample(/file)?',path)
    if sample:
        cid,code,file=sample.groups()
        if file:return self.serve_media(channel_translation_voices.audio_file(cid,code,(query.get('key') or [None])[0]))
        try:settings=json.loads(query['settings'][0]) if query.get('settings') else None
        except (ValueError,TypeError):raise store.StudioError('Невірні налаштування зразка') from None
        return self.json_response(channel_translation_voices.describe(cid,code,settings,(query.get('text') or [None])[0]))
    match = re.fullmatch(r'/api/channels/([0-9a-f]{16})/competitors', path)
    if match:
        return self.json_response({'competitors': channel_competitors.read(match.group(1))})

    transfer = re.fullmatch(r'/api/channels/([0-9a-f]{16})/settings-(export|backups)', path)
    if transfer:
        cid, kind = transfer.groups()
        if kind == 'backups': return self.json_response({'backups': channel_transfer.list_backups(cid)})
        ensure_idle(cid)
        raw = channel_transfer.export_bundle(cid)
        self.send_response(200)
        self.send_header('Content-Type', 'application/zip')
        self.send_header('Content-Disposition', 'attachment; filename="VideoKey-channel-settings.zip"')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(raw)
        return

    reference_match = re.fullmatch(r'/api/channels/([0-9a-f]{16})/idea-reference/([A-Za-z0-9_-]{11})/thumbnail', path)
    if reference_match:
        import idea_reference
        cid, ref = reference_match.groups()
        idea_reference.read(cid, ref)
        return self.serve_media(idea_reference.folder(cid, ref) / 'thumbnail.jpg')

    match = re.fullmatch(r'/api/channels/([0-9a-f]{16})/voice-lab(?:/(reference|sample|prepared|draft|heygen-voices|preview))?', path)
    if match:
        cid, kind = match.groups()
        if kind == 'preview':
            speed = (query.get('speed') or [None])[0]
            return self.serve_media(channel_voice_lab.tempo_preview(cid, speed) if speed is not None else channel_voice_lab.local_preview_source(cid))
        if kind=='heygen-voices':return self.json_response(channel_voice_lab.heygen_voice.voices((query.get('model') or ['heygen-voice-1'])[0]))
        if kind == 'draft':
            return self.serve_media(channel_voice_lab.reference_drafts.audio_file(channel_voice_lab.folder(cid), (query.get('id') or [None])[0], (query.get('clean') or ['0'])[0] == '1'))
        if kind:
            return self.serve_media(channel_voice_lab.audio_file(cid, kind, (query.get('key') or [None])[0]))
        return self.json_response(channel_voice_lab.snapshot(cid))

    ideas_match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/episode-ideas", path)
    if ideas_match:
        import episode_ideas
        data = episode_ideas.catalog(ideas_match.group(1)) if query.get('view') == ['topics'] else episode_ideas.read(ideas_match.group(1))
        return self.json_response(episode_ideas.public(data))

    if path == "/api/channels":
        return self.json_response({"channels": store.list_channels()})

    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/agent-memory", path)
    if match:
        return self.json_response({"memory": agent_storage.get_memory(match.group(1))})

    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/style-previews/([0-9a-f]{20})/([a-z0-9_-]+-\d\.jpg)", path)
    if match:
        store.get_channel_folder(match.group(1))
        try:
            return self.serve_media(style_lab.preview_file(*match.groups()), cache=True)
        except style_lab.StyleLabError as error:
            raise store.StudioError(str(error), 404) from None

    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/custom-styles", path)
    if match:
        return self.json_response({"styles": style_copy.load(match.group(1))})

    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/voices", path)
    if match:
        return self.json_response(languages.channel_voices(match.group(1)))

    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/voices/([a-z]{2})/file", path)
    if match:
        return self.serve_media(languages.channel_voice_file(*match.groups()))

    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/logo-overlay\.png", path)
    if match:
        folder = store.get_channel_folder(match.group(1))
        try:
            frame = (int((query.get("w") or ["1920"])[0]), int((query.get("h") or ["1080"])[0]))
        except ValueError:
            raise store.StudioError("Невірний розмір кадру") from None
        if not (16 <= frame[0] <= 7680 and 16 <= frame[1] <= 7680):
            raise store.StudioError("Невірний розмір кадру")
        settings = store.read_channel_settings(folder, {})
        target = store.DATA_ROOT / "channels" / match.group(1) / f"logo-overlay-{frame[0]}x{frame[1]}.png"
        if not channel_branding.overlay_png(match.group(1), settings.get("logo"), frame, target):
            raise store.StudioError("Логотип не додано або вимкнено", 404)
        return self.serve_media(target)

    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/(thumbnail-hero|icon|logo)", path)
    if match:
        cid, kind = match.groups()
        store.get_channel_folder(cid)
        read, message = {
            'thumbnail-hero': (channel_hero.path, 'Референс героя не додано'),
            'icon': (channel_branding.icon_path, 'Іконку не додано'),
            'logo': (channel_branding.logo_path, 'Логотип не додано'),
        }[kind]
        target = read(cid)
        if not target.is_file():
            raise store.StudioError(message, 404)
        return self.serve_media(target, cache=True)

    raise store.StudioError("Невідомий запит", 404)


def mutate(self, method, path, body, *, ensure_idle, choose_folder):
    match = re.fullmatch(r'/api/channels/([0-9a-f]{16})/competitors(?:/(UC[A-Za-z0-9_-]{22}))?', path)
    if match:
        cid, identity = match.groups()
        if method == 'POST' and not identity:
            return self.json_response(channel_competitors.add(cid, body.get('url')))
        if method == 'DELETE' and identity:
            return self.json_response(channel_competitors.remove(cid, identity))
        raise store.StudioError('Невідомий запит', 404)

    backup = re.fullmatch(r'/api/channels/([0-9a-f]{16})/settings-backups/([0-9a-f]{32})(/restore)?', path)
    if backup:
        cid, bid, restore = backup.groups()
        if method == 'POST' and restore:
            return self.json_response(channel_transfer.restore_backup(cid, bid, ensure_idle))
        if method == 'DELETE' and not restore:
            return self.json_response(channel_transfer.delete_backup(cid, bid))

    reference_match = re.fullmatch(r'/api/channels/([0-9a-f]{16})/idea-reference', path)
    if reference_match and method == 'POST':
        import idea_reference
        return self.json_response(idea_reference.inspect(reference_match.group(1), body.get('url')))

    match = re.fullmatch(r'/api/channels/([0-9a-f]{16})/voice-lab(?:/(sample|reference/remove|reference/preview|reference/accept|reference/discard|copy|heygen-clone|fish-clone))?', path)
    if match and method == 'POST':
        cid, action = match.groups()
        if action == 'heygen-clone':return self.json_response(channel_voice_lab.create_heygen_voice(cid, body.get('settings')))
        if action == 'fish-clone':return self.json_response(channel_voice_lab.create_fish_voice(cid, body.get('settings')))
        if action == 'reference/discard':
            with channel_voice_lab.LOCK:
                channel_voice_lab.reference_drafts.discard(channel_voice_lab.folder(cid), body.get('draft_id'))
            return self.json_response({'discarded': True})
        if action == 'reference/preview':return self.json_response(channel_voice_lab.preview_reference(cid, body.get('draft_id')))
        if action == 'reference/accept':return self.json_response(channel_voice_lab.accept_reference(cid, body.get('draft_id'), body.get('cleaned')))
        if action == 'copy':return self.json_response(channel_voice_lab.copy_profile(body.get('source_channel'), cid))
        if action == 'sample':
            return self.json_response(channel_voice_lab.start(cid, body.get('settings'), body.get('client_id')), 202)
        if action == 'reference/remove':return self.json_response(channel_voice_lab.remove(cid))
        return self.json_response(channel_voice_lab.save(cid, body.get('settings')))

    if method == "PATCH" and path == "/api/channels/order":
        return self.json_response({"channels": store.reorder_channels(body.get("ids"))})

    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/agent-memory", path)
    if match and method == "POST":
        return self.json_response({"memory": agent_storage.set_memory(match.group(1), body.get("memory"))})

    if method == "POST" and path == "/api/channels/pick":
        selected = Path(body["path"]).expanduser().resolve() if body.get("path") else choose_folder("Оберіть папку каналу всередині папки YouTube")
        return self.json_response({"channel": store.add_channel(selected, body.get("copy_from"))})

    if method == "POST" and path == "/api/channels/create":
        return self.json_response({"channel": store.create_channel(body["name"], body.get("copy_from"))}, 201)

    match=re.fullmatch(r'/api/channels/([0-9a-f]{16})/voices/settings',path)
    if match and method=='POST':return self.json_response(channel_translation_voices.save(match.group(1),body.get('languages')))
    match=re.fullmatch(r'/api/channels/([0-9a-f]{16})/voices/([a-z]{2})/sample',path)
    if match and method=='POST':return self.json_response(channel_translation_voices.start(*match.groups(),body.get('settings'),body.get('text'),body.get('client_id')),202)
    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/voices/([a-z]{2})/remove", path)
    if match and method == "POST":
        return self.json_response(languages.remove_channel_voice(*match.groups()))

    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/custom-styles", path)
    if match and method == "POST":
        try:
            style = style_copy.create(match.group(1), body.get("image"), body.get("note") or "")
        except style_copy.StyleCopyError as error:
            raise store.StudioError(str(error), 409) from None
        return self.json_response({"style": style}, 201)

    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/custom-styles/(custom-[0-9a-f]{10})", path)
    if match and method == "DELETE":
        try:
            style_copy.remove(*match.groups())
        except style_copy.StyleCopyError as error:
            raise store.StudioError(str(error), 404) from None
        return self.json_response({"ok": True})

    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/style-cards", path)
    if match and method == "POST":
        try:
            return self.json_response(style_lab.showcase(match.group(1), (body or {}).get("kind")))
        except style_lab.StyleLabError as error:
            raise store.StudioError(str(error), 409) from None

    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/style-previews", path)
    if match and method == "POST":
        try:
            return self.json_response(style_lab.previews(match.group(1), bool(body.get("assets", True)), body.get("animation"), body.get("style")))
        except style_lab.StyleLabError as error:
            raise store.StudioError(str(error), 409) from None

    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/thumbnail-hero", path)
    if match and method in {"POST", "DELETE"}:
        if method == "POST":
            hero = channel_hero.save(match.group(1), body.get("data"))
        else:
            channel_hero.remove(match.group(1))
            hero = None
        return self.json_response({"hero_reference": hero, "channels": store.list_channels()})

    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/icon", path)
    if match and method in {"POST", "DELETE"}:
        try:
            if method == "POST":
                icon = channel_branding.save_logo(match.group(1), body.get("data"), identity_icon=True)
            else:
                channel_branding.remove_icon(match.group(1))
                icon = None
            return self.json_response({"icon": icon, "channels": store.list_channels()})
        except channel_branding.BrandingError as error:
            raise store.StudioError(str(error)) from None

    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/logo", path)
    if match and method in {"POST", "DELETE"}:
        try:
            if method == "POST":
                return self.json_response({"logo": channel_branding.save_logo(match.group(1), body.get("data"))}, 201)
            channel_branding.remove_logo(match.group(1))
            return self.json_response({"logo": None})
        except channel_branding.BrandingError as error:
            raise store.StudioError(str(error)) from None

    match = re.fullmatch(r"/api/channels/([0-9a-f]{16})", path)
    if match and method == "PATCH":
        return self.json_response({"channel": store.update_channel_settings(match.group(1), body.get("settings", {}))})

    if match and method == "DELETE":
        store.disable_channel(match.group(1))
        return self.json_response({"ok": True})

    ideas_match = re.fullmatch(r"/api/channels/([0-9a-f]{16})/episode-ideas", path)
    if ideas_match and method == "POST":
        import episode_ideas
        return self.json_response(episode_ideas.public(episode_ideas.start(ideas_match.group(1), body)), 202)

    raise store.StudioError("Невідомий запит", 404)
