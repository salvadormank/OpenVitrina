"""
video_concat.py
───────────────
Une los clips de IA con transiciones y añade música.
"""
from __future__ import annotations
import os
import numpy as np
import moviepy.editor as mpy
from moviepy.video.fx.all import fadein, fadeout
from PIL import Image as PilImage
PilImage.ANTIALIAS = PilImage.LANCZOS  # fix Pillow 10+



TRANS = 0.8  # segundos de crossfade


def _crossfade(clips):
    if len(clips) == 1:
        return clips[0]
    return mpy.concatenate_videoclips(clips, method='compose', padding=-TRANS)


def _fade_black(clips):
    out = []
    for c in clips:
        c = fadein(c, TRANS / 2)
        c = fadeout(c, TRANS / 2)
        out.append(c)
    return mpy.concatenate_videoclips(out, method='chain')


def _wipe(clips):
    if len(clips) == 1:
        return clips[0]
    result = clips[0]
    for nxt in clips[1:]:
        W, H = result.size
        dur  = TRANS

        def make(t, _a=result, _b=nxt):
            p  = t / dur
            x  = int(W * p)
            fa = _a.get_frame(_a.duration - dur + t)
            fb = _b.get_frame(t)
            out = fa.copy()
            out[:, :x] = fb[:, :x]
            return out

        trans   = mpy.VideoClip(make, duration=dur).set_fps(result.fps)
        before  = result.subclip(0, result.duration - dur)
        after   = nxt.subclip(dur)
        result  = mpy.concatenate_videoclips([before, trans, after], method='chain')
    return result


def _zoom(clips):
    out = []
    for c in clips:
        c = fadein(c, TRANS * 0.4)
        c = fadeout(c, TRANS * 0.4)
        out.append(c)
    return mpy.concatenate_videoclips(out, method='compose', padding=-TRANS * 0.4)


TRANSITIONS = {
    'crossfade':  _crossfade,
    'fade_black': _fade_black,
    'wipe_right': _wipe,
    'zoom_blur':  _zoom,
}


def concat_clips_with_music(clip_paths, output_path, music_path,
                             transition='crossfade', fps=30, progress_callback=None):
    if not clip_paths:
        raise ValueError('Sin clips.')

    if progress_callback: progress_callback(5)

    # Cargar clips
    clips = [mpy.VideoFileClip(p).set_fps(fps) for p in clip_paths]

    # Normalizar tamaño
    W, H = clips[0].size
    clips = [c.resize((W, H)) if c.size != (W, H) else c for c in clips]

    if progress_callback: progress_callback(20)

    # Aplicar transición
    fn = TRANSITIONS.get(transition, _crossfade)
    try:
        video = fn(clips)
    except Exception:
        video = _crossfade(clips)

    video = fadein(video, 0.5)
    video = fadeout(video, 1.0)

    if progress_callback: progress_callback(55)

    # Música
    if music_path and os.path.exists(music_path):
        dur   = video.duration
        audio = mpy.AudioFileClip(music_path)
        if audio.duration < dur:
            loops = int(np.ceil(dur / audio.duration))
            audio = mpy.concatenate_audioclips([audio] * loops)
        audio = audio.subclip(0, dur).audio_fadein(1.5).audio_fadeout(min(3.0, dur * 0.1))
        video = video.set_audio(audio)

    if progress_callback: progress_callback(65)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    video.write_videofile(
        output_path, fps=fps, codec='libx264', audio_codec='aac',
        preset='ultrafast', ffmpeg_params=['-crf', '18'], logger=None,
    )

    if progress_callback: progress_callback(100)

    video.close()
    for c in clips:
        try: c.close()
        except: pass

    return output_path
