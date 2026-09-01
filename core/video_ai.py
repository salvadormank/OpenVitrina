"""
video_ai.py
───────────
Genera un clip de video cinemático a partir de una imagen.

Soporta:
  OpenAI Sora 2  →  usa OPENAI_API_KEY
  fal.ai Kling   →  usa FAL_KEY
"""
from __future__ import annotations
import os, time, logging, requests, tempfile
from pathlib import Path
from PIL import Image

logger = logging.getLogger(__name__)

OPENAI_MODELS = {'sora-2', 'sora-2-pro'}

FAL_PARAMS = {
    'fal-ai/kling-video/o3/standard/image-to-video': {'duration': '5', 'aspect_ratio': '9:16'},
    'fal-ai/kling-video/o3/pro/image-to-video':      {'duration': '5', 'aspect_ratio': '9:16'},
    'fal-ai/kling-video/v1.6/standard/image-to-video':{'duration': '5', 'aspect_ratio': '9:16'},
    'fal-ai/minimax/video-01/image-to-video':         {'aspect_ratio': '9:16'},
    'fal-ai/runway-gen3/turbo/image-to-video':        {'duration': 5, 'ratio': '768:1280'},
}


def _setting(name, default=None):
    try:
        from django.conf import settings
        return getattr(settings, name, default)
    except Exception:
        return default


def _mime(path):
    return {'.jpg':'image/jpeg','.jpeg':'image/jpeg',
            '.png':'image/png','.webp':'image/webp'}.get(Path(path).suffix.lower(), 'image/jpeg')


def _download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    r = requests.get(url, stream=True, timeout=300)
    r.raise_for_status()
    with open(dest, 'wb') as f:
        for chunk in r.iter_content(8192):
            if chunk:
                f.write(chunk)


def _resize_for_sora(image_path, width=720, height=1280):
    """
    Redimensiona la imagen a 720x1280 (requerido por Sora).
    Hace crop centrado para no distorsionar.
    Retorna ruta de archivo temporal.
    """
    img = Image.open(image_path).convert('RGB')
    orig_w, orig_h = img.size

    # Escalar para cubrir el tamaño destino
    scale = max(width / orig_w, height / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Crop centrado
    left = (new_w - width) // 2
    top  = (new_h - height) // 2
    img  = img.crop((left, top, left + width, top + height))

    tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    img.save(tmp.name, 'JPEG', quality=95)
    tmp.close()
    return tmp.name


# ── OpenAI Sora ────────────────────────────────────────────────────────────────
_SORA_FALLBACK_PROMPT = "Smooth cinematic motion, natural lighting, gentle camera movement."

def _sora(image_path, output_path, prompt, model, on_update):
    return _sora_request(image_path, output_path, prompt, model, on_update)

def _sora_request(image_path, output_path, prompt, model, on_update, _retry=False):
    key = os.environ.get('OPENAI_API_KEY') or _setting('OPENAI_API_KEY', '')
    if not key:
        raise RuntimeError('OPENAI_API_KEY no configurada en .env')
    headers = {'Authorization': f'Bearer {key}'}
    if on_update:
        on_update('Preparando imagen…')
    resized_path = _resize_for_sora(image_path)
    if on_update:
        on_update('Enviando imagen a OpenAI Sora…')
    try:
        with open(resized_path, 'rb') as f:
            r = requests.post(
                'https://api.openai.com/v1/videos',
                headers=headers,
                files={'input_reference': (Path(resized_path).name, f, 'image/jpeg')},
                data={'model': model, 'prompt': prompt, 'size': '720x1280', 'seconds': '4'},
                timeout=60,
            )
    finally:
        try:
            os.unlink(resized_path)
        except Exception:
            pass
    if r.status_code not in (200, 201, 202):
        raise RuntimeError(f'OpenAI error {r.status_code}: {r.text}')
    job_id = r.json().get('id') or r.json().get('video_id')
    if not job_id:
        raise RuntimeError(f'Sin job ID: {r.json()}')
    for i in range(120):
        time.sleep(5)
        if on_update:
            on_update(f'Sora generando… {i * 5}s')
        s = requests.get(f'https://api.openai.com/v1/videos/{job_id}',
                         headers=headers, timeout=30)
        s.raise_for_status()
        data   = s.json()
        status = data.get('status', '')
        if status == 'completed':
            url = data.get('url') or data.get('video_url') or (data.get('output') or {}).get('url')
            if url:
                _download(url, output_path)
            else:
                dl = requests.get(f'https://api.openai.com/v1/videos/{job_id}/content',
                                  headers=headers, stream=True, timeout=300)
                dl.raise_for_status()
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'wb') as f:
                    for chunk in dl.iter_content(8192):
                        if chunk:
                            f.write(chunk)
            return output_path
        elif status in ('failed', 'error', 'cancelled'):
            error = data.get('error') or status
            if (
                not _retry
                and isinstance(error, dict)
                and error.get('code') == 'moderation_blocked'
            ):
                import logging
                logging.getLogger(__name__).warning(
                    f'Sora moderation_blocked — prompt original: "{prompt[:120]}" | '
                    f'Reintentando con prompt fallback.'
                )
                return _sora_request(
                    image_path, output_path,
                    _SORA_FALLBACK_PROMPT,
                    model, on_update,
                    _retry=True,
                )
            raise RuntimeError(f'Sora falló: {error}')
    raise RuntimeError('Sora timeout (>10 min)')







# ── fal.ai ─────────────────────────────────────────────────────────────────────
def _fal(image_path, output_path, prompt, model, on_update):
    try:
        import fal_client
    except ImportError:
        raise RuntimeError('Ejecuta: pip install fal-client')

    key = os.environ.get('FAL_KEY') or _setting('FAL_KEY', '')
    if not key:
        raise RuntimeError('FAL_KEY no configurada en .env')
    os.environ['FAL_KEY'] = key

    if on_update:
        on_update('Subiendo imagen a fal.ai…')

    with open(image_path, 'rb') as f:
        img_url = fal_client.upload(f, content_type=_mime(image_path))

    args = {'image_url': img_url, 'prompt': prompt,
            'negative_prompt': 'blur, distortion, watermark, text, ugly',
            **FAL_PARAMS.get(model, {})}

    def _cb(u):
        if on_update:
            on_update(str(getattr(u, 'message', u)))

    result = fal_client.subscribe(model, arguments=args, with_logs=True, on_queue_update=_cb)

    url = None
    if hasattr(result, 'video') and hasattr(result.video, 'url'):
        url = result.video.url
    elif isinstance(result, dict):
        v = result.get('video', {})
        url = (v.get('url') if isinstance(v, dict) else v) or result.get('video_url')

    if not url:
        raise RuntimeError(f'fal.ai sin URL de video: {result}')

    _download(url, output_path)
    return output_path


# ── Función principal ──────────────────────────────────────────────────────────
def generate_clip_from_image(image_path, output_path, prompt,
                              model=None, on_queue_update=None):
    model = model or _setting('AI_VIDEO_MODEL', 'sora-2')
    logger.info(f'Generando clip — modelo: {model}')

    if model in OPENAI_MODELS:
        return _sora(image_path, output_path, prompt, model, on_queue_update)
    else:
        return _fal(image_path, output_path, prompt, model, on_queue_update)
