"""
Transcripción y subtítulos quemados.

Whisper corre local: no cuesta nada por uso y no manda el audio a ningún lado.
Importante para reels, donde la mayoría se ven sin sonido.
"""

import logging
import textwrap

import moviepy.editor as mpy

logger = logging.getLogger(__name__)

W, H = 1080, 1920

# Estilo de subtítulo. Blanco con contorno negro grueso: legible sobre
# cualquier fondo, que es la razón por la que todos los reels lo usan.
FONT_SIZE = 64
FONT = 'Arial-Bold'
COLOR = 'white'
STROKE = 'black'
STROKE_W = 4
MAX_CHARS = 32          # por línea, para que no invada los lados
BOTTOM_MARGIN = 420     # sube el texto sobre la zona de la interfaz de TikTok/IG


def transcribe(audio_or_video_path, model_size='base', language=None):
    """
    Devuelve (segmentos, idioma). Cada segmento es {'start','end','text'}.
    Devuelve ([], None) si Whisper no está instalado.
    """
    try:
        import whisper
    except ImportError:
        logger.warning('whisper no instalado — sin subtítulos. '
                       'pip install openai-whisper')
        return [], None

    logger.info(f'Transcribiendo con Whisper "{model_size}"…')
    model = whisper.load_model(model_size)
    result = model.transcribe(audio_or_video_path, language=language,
                              verbose=False)
    segs = [{'start': s['start'], 'end': s['end'], 'text': s['text'].strip()}
            for s in result.get('segments', []) if s.get('text', '').strip()]
    logger.info(f'{len(segs)} segmentos, idioma detectado: {result.get("language")}')
    return segs, result.get('language')


def segments_to_subtitles(segments, max_chars=MAX_CHARS):
    """Convierte segmentos de Whisper en (inicio, fin, texto) con saltos de línea."""
    out = []
    for s in segments:
        text = '\n'.join(textwrap.wrap(s['text'], max_chars)) or s['text']
        out.append((s['start'], s['end'], text))
    return out


def _text_clip(text, duration):
    try:
        return mpy.TextClip(
            text, fontsize=FONT_SIZE, font=FONT, color=COLOR,
            stroke_color=STROKE, stroke_width=STROKE_W,
            method='label', align='center',
        ).set_duration(duration)
    except Exception as exc:
        # ImageMagick no disponible o fuente faltante
        logger.warning(f'No se pudo renderizar el subtítulo ({exc})')
        return None


def burn_subtitles(clip, subtitles):
    """Superpone los subtítulos sobre el clip. Devuelve el clip original si falla."""
    layers = [clip]
    for start, end, text in subtitles:
        dur = max(end - start, 0.4)
        tc = _text_clip(text, dur)
        if tc is None:
            return clip
        layers.append(
            tc.set_start(start)
              .set_position(('center', H - BOTTOM_MARGIN))
        )
    if len(layers) == 1:
        return clip
    return mpy.CompositeVideoClip(layers, size=(W, H)).set_duration(clip.duration)


def write_srt(subtitles, path):
    """Guarda un .srt aparte, por si el usuario prefiere subirlo a la plataforma."""
    def ts(t):
        h, rem = divmod(t, 3600)
        m, s = divmod(rem, 60)
        return f'{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}'

    with open(path, 'w', encoding='utf-8') as f:
        for i, (start, end, text) in enumerate(subtitles, 1):
            f.write(f'{i}\n{ts(start)} --> {ts(end)}\n{text}\n\n')
    return path
