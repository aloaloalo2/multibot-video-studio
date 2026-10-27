# MultiBot Video Studio render engine

This is the first local export engine for the Video Studio app. It composes editable project manifests into MP4 using the installed FFmpeg, FFprobe, and Pillow. The input media is read only. It does not call HyperFrames or a cloud service.

## Run

```bash
python3 engine/render.py --project /path/to/project.json --output /path/to/episode/video.mp4
python3 engine/render.py --project /path/to/project.json --validate-only
```

The renderer writes JSON progress events to stdout, including `validated`, `scene_start`, `scene_done`, `compose`, `complete`, and `error`. A failed or cancelled job removes its temporary output. An existing output is never replaced. A successful export is fully decoded for a technical check before the completed MP4 appears atomically at the requested path.

## Manifest

Paths may be absolute or relative to the manifest file. Scenes are listed in playback order and begin at time zero. The outgoing transition belongs to the scene before the cut.

### Universal timeline (current format)

Every layer is universal. It can contain visual and audio clips. A greater `z` draws visual clips on top of lower layers. Clips can overlap in time and can be moved between layers without changing their type. Clip starts and durations are rounded to the nearest output frame.

```json
{
  "width": 1920, "height": 1080, "fps": 30, "background": "#101114",
  "timeline_layers": [
    {"id": "layer-1", "z": 0, "clips": [
      {"id": "opening", "type": "video", "source": "media/opening.mp4", "start": 0,
       "duration": 8, "trim_start": 2, "volume": 0,
       "transition": {"type": "crossfade", "duration": 0.4}},
      {"id": "photo", "type": "image", "source": "media/photo.jpg", "start": 7.6, "duration": 5}
    ]},
    {"id": "layer-2", "z": 1, "clips": [
      {"id": "headline", "type": "text", "text": "Важлива теза", "start": 1, "duration": 3,
       "x": 0.5, "y": 0.5, "width": 0.8, "height": 0.3, "preset": "pop",
       "keyframes": [{"time": 0, "opacity": 0}, {"time": 0.5, "opacity": 1}]},
      {"id": "arrow", "type": "animation", "source": "media/arrow.png", "start": 5,
       "duration": 2, "x": 100, "y": 200, "width": 250, "height": 120,
       "keyframes": [{"time": 0, "x": 100, "scale": 0.8}, {"time": 2, "x": 620, "scale": 1.2}]}
    ]},
    {"id": "layer-3", "z": 2, "clips": [
      {"id": "voice", "type": "audio", "source": "media/voice.wav", "start": 0,
       "duration": 12.6, "trim_start": 0, "volume": 1}
    ]}
  ]
}
```

Supported clip types: `video`, `image`, `text`, `audio`, `animation`. An `animation` clip may set `content_type` to `image`, `video`, `text`, or `shape`. Without that field, a `source` selects image/video by extension, `text` selects text, and neither creates a colored rectangle. All visual clips support `x`, `y`, `width`, `height`, `opacity`, `scale`, and `keyframes` of `x`, `y`, `scale`, and `opacity`, linearly interpolated by clip-local `time`. Universal clips use normalized coordinates by default: `x=0.5,y=0.5` centers the clip, and `width=1,height=1` fills the canvas. Values outside 0..1 can place or scale a clip beyond the frame. Set `units:"px"` on a clip to use pixel coordinates and a top-left anchor. Animation presets: `fade_in`, `fade_out`, `slide_in`, `slide_out`, `zoom_in`, `pop`, with optional `preset_duration` (default 0.4 seconds). These are directly rendered, including on regular image/video/text clips.

`transition` belongs to the outgoing visual clip and targets the next visual clip on the same layer. Supported types: `cut`, `crossfade`, `swipe` (`wipe` alias). A transition needs clips that touch or overlap for at least its duration. When clips overlap, the incoming clip fades or slides over the outgoing clip. At a direct cut, both clips animate at their edges without moving their timeline positions. A gap with a transition is rejected. Audio clips may be placed on any layer. A video clip with an audio stream contributes sound only when its `volume` is greater than zero; the default video volume is zero. An audio clip defaults to volume one. No audio clips yields a silent AAC track.

The engine also accepts the earlier ordered-scene format below for existing projects.

### Ordered scenes (legacy format)

```json
{
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "scenes": [
    {
      "id": "opening",
      "type": "video",
      "source": "media/opening.mp4",
      "trim_start": 0,
      "duration": 8,
      "transition_out": {"type": "crossfade", "duration": 0.35},
      "layers": [
        {"type": "text", "text": "Важлива теза", "x": 110, "y": 90, "font_size": 64, "start": 3, "duration": 3},
        {"type": "image", "source": "media/arrow.png", "x": 900, "y": 300, "width": 160, "height": 110,
         "keyframes": [{"time": 0, "x": 900}, {"time": 1.2, "x": 1080}]}
      ]
    },
    {"id": "next", "type": "image", "source": "media/next.jpg", "duration": 6}
  ],
  "tracks": [
    {"kind": "voice", "source": "media/voice.wav", "start": 0, "trim_start": 0, "duration": 14, "volume": 1},
    {"kind": "music", "source": "media/music.mp3", "start": 0, "volume": 0.15, "loop": true}
  ]
}
```

Scene types: `video`, `image`, `text`, and `color`. A text scene may set `text` directly; text is rasterized to a transparent layer with a local Unicode font. Visual layers support `image`, `video`, and `text`. `layer.start` and `layer.duration` are relative to the scene. Layer position and size are in pixels, or normalized 0..1 when provided as JSON floats. Normalized text positions use a centered anchor. Text fits to the requested width and height by reducing font size; content that cannot fit is rejected rather than clipped. Static `width`,`height` and `opacity` are supported. Position keyframes linearly interpolate `x` and `y` by scene-local `time`. A layer whose time interval lies outside its scene is skipped. The first version supports `cut` and `crossfade` transitions. A video scene must not run past its source's remaining duration; the engine rejects that plan rather than freezing the last frame.

Audio tracks are a flat list. `kind` is informational; `source`, `start`, `trim_start`, `duration`, `volume` (0..5), and optional `loop` control playback. When no audio is present, export contains a silent stereo AAC track. Source video sound is ignored so it cannot accidentally replace the approved narration.

## Limits of this version

The current engine renders timeline slices to temporary segments, concatenates them, and mixes the audio. Text uses a rasterized image in the MP4; the project JSON remains editable. Keyframes cover position, scale, and opacity. Curves, masks, motion blur, and advanced effects are future work. Both manifest formats support cut, crossfade, and swipe. This implementation has been tested with short synthetic projects and a 40-scene tiny project, including a fully decoded output. Long real channel episodes and relative render speed against HyperFrames require an end-to-end benchmark. The export test is technical QA, not a human viewing or listening test.

## Tests

Native frame joins also support 15 cinematic dissolves defined in `frontend/graphic-transitions.json`. The editor and renderer use the same animated light and dissolve settings without adding camera motion. Their translucent overlays are rendered above scene media and below permanent branding, with the original audio left intact.

```bash
python3 -m unittest discover -s engine/tests -v
```

The integration suite creates synthetic image, video, and audio assets; verifies legacy scenes, universal layers, overlapping clips, timed text, position/scale/opacity animation, transitions, audio, full decoding, and failure without output when media is missing.
