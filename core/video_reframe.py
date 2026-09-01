"""
Reencuadre de video horizontal a vertical 9:16.

A diferencia de video_ai.py, aquí no se genera nada: se recorta y reencuadra
material que el usuario ya tiene. Es gratis y corre en segundos.

Tres modos:
  center  — recorte fijo al centro. Rápido y predecible.
  smart   — sigue al sujeto usando detección de rostros (requiere opencv).
            Cae a 'center' si opencv no está instalado o no detecta nada.
  padded  — video completo centrado sobre un fondo desenfocado. No corta nada.
"""

import logging

import numpy as np
import moviepy.editor as mpy

logger = logging.getLogger(__name__)

W, H = 1080, 1920          # 9:16
TARGET_AR = W / H


# ── utilidades ───────────────────────────────────────────────────────────────
def _needs_reframe(clip):
    return abs(clip.w / clip.h - TARGET_AR) > 0.01


def _crop_width(clip):
    """Ancho de la franja vertical que cabe en el clip."""
    return min(clip.w, int(round(clip.h * TARGET_AR)))


def _smooth(xs, window=15):
    """Media móvil, para que el encuadre no tiemble entre cuadros."""
    if len(xs) < 3:
        return xs
    k = np.ones(min(window, len(xs))) / min(window, len(xs))
    return np.convolve(np.asarray(xs, dtype=float), k, mode='same')


# ── modo center ──────────────────────────────────────────────────────────────
def _center(clip):
    cw = _crop_width(clip)
    return clip.crop(x_center=clip.w / 2, width=cw).resize((W, H))


# ── modo smart ───────────────────────────────────────────────────────────────
def _track_subject(clip, samples=60):
    """
    Devuelve, para tiempos equiespaciados, la x del sujeto detectado.
    Usa el detector de rostros de opencv; si no hay rostro, cae al centro.
    """
    try:
        import cv2
    except ImportError:
        logger.info('opencv no instalado — modo smart cae a center')
        return None

    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    if cascade.empty():
        return None

    times = np.linspace(0, max(clip.duration - 0.01, 0), samples)
    xs, hits = [], 0
    for t in times:
        frame = clip.get_frame(t)
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        faces = cascade.detectMultiScale(gray, 1.2, 5, minSize=(60, 60))
        if len(faces):
            x, _, fw, _ = max(faces, key=lambda f: f[2] * f[3])
            xs.append(x + fw / 2); hits += 1
        else:
            xs.append(xs[-1] if xs else clip.w / 2)

    if hits < samples * 0.15:
        logger.info(f'Sujeto detectado en solo {hits}/{samples} muestras — usando center')
        return None
    return times, _smooth(xs)


def _smart(clip):
    tracked = _track_subject(clip)
    if tracked is None:
        return _center(clip)

    times, xs = tracked
    cw = _crop_width(clip)
    half = cw / 2
    lo, hi = half, clip.w - half

    def x_at(t):
        return float(np.clip(np.interp(t, times, xs), lo, hi))

    def make(get_frame, t):
        frame = get_frame(t)
        cx = x_at(t)
        a = int(round(cx - half))
        a = max(0, min(a, clip.w - cw))
        return frame[:, a:a + cw]

    return clip.fl(make, apply_to=['mask']).resize((W, H))


# ── modo padded ──────────────────────────────────────────────────────────────
def _padded(clip):
    fg = clip.resize(width=W)
    bg = (clip.resize(height=H)
              .crop(x_center=clip.resize(height=H).w / 2, width=W)
              .fx(mpy.vfx.colorx, 0.55))
    try:
        bg = bg.fx(mpy.vfx.headblur, 0, 0, 0)   # no-op seguro si falta scipy
    except Exception:
        pass
    return mpy.CompositeVideoClip([bg, fg.set_position('center')],
                                  size=(W, H)).set_duration(clip.duration)


# ── API pública ──────────────────────────────────────────────────────────────
MODES = {'center': _center, 'smart': _smart, 'padded': _padded}


def reframe_clip(clip, mode='smart'):
    """Devuelve el clip reencuadrado a 1080x1920."""
    if not _needs_reframe(clip):
        return clip.resize((W, H))
    fn = MODES.get(mode, _center)
    try:
        return fn(clip)
    except Exception as exc:
        logger.warning(f'Reencuadre "{mode}" falló ({exc}) — usando center')
        return _center(clip)


def reframe_video(src_path, output_path, mode='smart', fps=30,
                  subtitles=None, progress_callback=None):
    """
    Convierte un video a formato reel vertical.

    subtitles: lista de (inicio, fin, texto) o None.
    """
    if progress_callback:
        progress_callback('Abriendo video…')
    clip = mpy.VideoFileClip(src_path)

    if progress_callback:
        progress_callback(f'Reencuadrando a 9:16 (modo {mode})…')
    out = reframe_clip(clip, mode)

    if subtitles:
        from .video_subtitles import burn_subtitles
        if progress_callback:
            progress_callback('Añadiendo subtítulos…')
        out = burn_subtitles(out, subtitles)

    if progress_callback:
        progress_callback('Exportando…')
    out.set_fps(fps).write_videofile(
        output_path, codec='libx264', audio_codec='aac',
        threads=4, logger=None)

    for c in (out, clip):
        try:
            c.close()
        except Exception:
            pass
    return output_path


def split_by_silence(src_path, max_len=60, min_len=15, segments=None):
    """
    Corta un video largo en trozos aptos para reel, respetando pausas del habla.

    `segments` son los segmentos de Whisper; sin ellos, corta cada `max_len`.
    Devuelve una lista de (inicio, fin).
    """
    clip = mpy.VideoFileClip(src_path)
    dur = clip.duration
    clip.close()

    if not segments:
        return [(t, min(t + max_len, dur))
                for t in np.arange(0, dur, max_len) if dur - t >= min_len]

    cuts, start = [], 0.0
    for seg in segments:
        end = seg['end']
        if end - start >= max_len:
            cuts.append((start, end))
            start = end
    if dur - start >= min_len:
        cuts.append((start, dur))
    return cuts
