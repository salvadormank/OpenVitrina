"""
tasks.py — Tarea Celery que genera el reel completo.
Por cada imagen: llama a la IA → descarga clip.
Al final: concatena clips + música → video final.
"""
from __future__ import annotations
import os, logging
from pathlib import Path
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


def _save(project, pct, msg='', extra=None):
    project.progress     = pct
    project.progress_msg = msg
    fields = ['progress', 'progress_msg'] + (extra or [])
    project.save(update_fields=fields)


@shared_task(bind=True, max_retries=1, time_limit=3600, name='core.tasks.reframe_video_project')
def reframe_video_project(self, project_id):
    """
    Convierte un video existente en un reel vertical.

    A diferencia de generate_reel, esto no llama a ningún modelo de IA de pago:
    solo recorta, opcionalmente transcribe con Whisper (local) y exporta.
    """
    import os
    from django.conf import settings as dj
    from .video_reframe import reframe_video
    from .video_subtitles import transcribe, segments_to_subtitles, write_srt

    try:
        project = VideoProject.objects.get(id=project_id)
    except VideoProject.DoesNotExist:
        logger.error(f'Proyecto {project_id} no existe')
        return

    project.status = 'generating'
    project.task_id = self.request.id
    project.error_msg = ''
    _save(project, 2, 'Iniciando…', ['status', 'task_id', 'error_msg'])

    if not project.source_video:
        project.status = 'error'
        project.error_msg = 'No hay video de origen'
        _save(project, 0, project.error_msg, ['status', 'error_msg'])
        return

    src = project.source_video.path
    out_dir = os.path.join(dj.MEDIA_ROOT, 'videos')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'{project.id}.mp4')

    subs = None
    try:
        if project.subtitles:
            _save(project, 15, 'Transcribiendo audio…')
            segments, _lang = transcribe(src)
            if segments:
                subs = segments_to_subtitles(segments)
                srt_dir = os.path.join(dj.MEDIA_ROOT, 'srt')
                os.makedirs(srt_dir, exist_ok=True)
                srt_path = os.path.join(srt_dir, f'{project.id}.srt')
                write_srt(subs, srt_path)
                project.srt_file.name = f'srt/{project.id}.srt'
                _save(project, 40, f'{len(subs)} subtítulos', ['srt_file'])

        reframe_video(
            src, out_path,
            mode=project.reframe_mode,
            subtitles=subs,
            progress_callback=lambda m: _save(project, min(project.progress + 8, 95), m),
        )
    except Exception as exc:
        logger.exception(f'Error reencuadrando: {exc}')
        project.status = 'error'
        project.error_msg = str(exc)[:2000]
        _save(project, 0, project.error_msg, ['status', 'error_msg'])
        return

    project.status = 'done'
    project.video_file.name = f'videos/{project.id}.mp4'
    _save(project, 100, '¡Reel listo!', ['status', 'video_file'])


@shared_task(bind=True, max_retries=1, time_limit=3600, name='core.tasks.generate_reel')
def generate_reel(self, project_id):
    from django.conf import settings
    from .models import VideoProject
    from .video_ai import generate_clip_from_image
    from .video_concat import concat_clips_with_music

    try:
        project = VideoProject.objects.get(pk=project_id)
    except VideoProject.DoesNotExist:
        return {'status': 'error', 'error': 'Proyecto no encontrado'}

    project.status    = 'generating'
    project.task_id   = self.request.id
    project.error_msg = ''
    _save(project, 2, 'Iniciando…', ['status', 'task_id', 'error_msg'])

    images = list(project.images.all())
    if not images:
        project.status    = 'error'
        project.error_msg = 'Sin imágenes.'
        _save(project, 0, project.error_msg, ['status', 'error_msg'])
        return {'status': 'error'}

    n          = len(images)
    prompt     = project.get_effective_prompt()
    model      = project.get_effective_model()
    clips_dir  = Path(settings.MEDIA_ROOT) / 'clips' / str(project_id)
    clips_dir.mkdir(parents=True, exist_ok=True)

    # ── Música ────────────────────────────────────────────────────────────────
    BUILTIN = {
        'cinematic': 'static/music/cinematic.wav',
        'upbeat':    'static/music/upbeat.wav',
        'luxury':    'static/music/luxury.wav',
    }
    music_path = None
    if project.music_choice == 'upload' and project.music_file:
        music_path = project.music_file.path
    elif project.music_choice in BUILTIN:
        p = Path(settings.BASE_DIR) / BUILTIN[project.music_choice]
        if p.exists():
            music_path = str(p)

    # ── Generar clips ─────────────────────────────────────────────────────────
    clip_paths = []
    step = 70 / n

    for idx, img in enumerate(images):
        out = str(clips_dir / f'clip_{img.order:03d}_{img.pk}.mp4')

        # Reusar si ya existe
        if img.clip_status == 'done' and img.clip_file and os.path.exists(img.clip_file.path):
            clip_paths.append(img.clip_file.path)
            pct = int(5 + (idx + 1) * step)
            _save(project, pct, f'Clip {idx+1}/{n} reutilizado')
            continue

        img.clip_status = 'generating'
        img.save(update_fields=['clip_status'])

        try:
            def on_update(msg, _i=idx):
                _save(project, project.progress, f'Clip {_i+1}/{n}: {msg}')
                self.update_state(state='PROGRESS', meta={'progress': project.progress})

            generate_clip_from_image(
                image_path      = img.image.path,
                output_path     = out,
                prompt          = prompt,
                model           = model,
                on_queue_update = on_update,
            )

            rel = Path(out).relative_to(settings.MEDIA_ROOT)
            img.clip_file.name = str(rel)
            img.clip_status    = 'done'
            img.clip_error     = ''
            img.save(update_fields=['clip_file', 'clip_status', 'clip_error'])
            clip_paths.append(out)

        except Exception as exc:
            logger.exception(f'Error clip {idx+1}: {exc}')
            img.clip_status = 'error'
            img.clip_error  = str(exc)
            img.save(update_fields=['clip_status', 'clip_error'])

        pct = int(5 + (idx + 1) * step)
        _save(project, pct, f'Clip {idx+1}/{n} listo')
        self.update_state(state='PROGRESS', meta={'progress': pct})

    if not clip_paths:
        project.status    = 'error'
        project.error_msg = 'Ningún clip fue generado.'
        _save(project, 0, project.error_msg, ['status', 'error_msg'])
        return {'status': 'error'}

    # ── Concatenar ────────────────────────────────────────────────────────────
    project.status = 'concat'
    _save(project, 76, 'Ensamblando video final…', ['status'])

    out_dir   = Path(settings.MEDIA_ROOT) / 'videos'
    out_dir.mkdir(parents=True, exist_ok=True)
    final_out = str(out_dir / f'{project_id}.mp4')

    def concat_progress(pct):
        overall = 76 + int(pct * 0.22)
        _save(project, overall, 'Ensamblando y añadiendo música…')

    try:
        concat_clips_with_music(
            clip_paths        = clip_paths,
            output_path       = final_out,
            music_path        = music_path,
            transition        = project.transition,
            progress_callback = concat_progress,
        )
    except Exception as exc:
        logger.exception(f'Error concat: {exc}')
        project.status    = 'error'
        project.error_msg = str(exc)
        _save(project, 0, project.error_msg, ['status', 'error_msg'])
        return {'status': 'error'}

    rel = Path(final_out).relative_to(settings.MEDIA_ROOT)
    project.video_file.name = str(rel)
    project.status          = 'done'
    _save(project, 100, '¡Video listo!', ['status', 'video_file'])

    return {'status': 'done', 'video_url': project.get_video_url()}
