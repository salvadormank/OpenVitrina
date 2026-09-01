from django.db import models
from django.contrib.auth.models import User
import uuid


def img_path(instance, filename):
    return f'uploads/{instance.project.id}/{filename}'

def music_path(instance, filename):
    return f'uploads/{instance.id}/music/{filename}'


class VideoProject(models.Model):

    STATUS = [
        ('draft',      'Borrador'),
        ('queued',     'En cola'),
        ('generating', 'Generando clips'),
        ('concat',     'Ensamblando'),
        ('done',       'Listo'),
        ('error',      'Error'),
    ]
    TRANSITIONS = [
        ('crossfade',  '✨ Crossfade suave'),
        ('fade_black', '⬛ Fundido a negro'),
        ('wipe_right', '➡️ Barrido'),
        ('zoom_blur',  '🔍 Zoom blur'),
    ]
    MUSIC_CHOICES = [
        ('cinematic', '🎼 Cinemático'),
        ('upbeat',    '🎵 Inspiracional'),
        ('luxury',    '🎹 Lujo'),
        ('upload',    '📤 Mi música'),
        ('none',      '🔇 Sin música'),
    ]
    SOURCE_TYPES = [
        ('photos', '🖼️ Fotos → video con IA'),
        ('video',  '🎬 Video existente → reel'),
    ]
    REFRAME_MODES = [
        ('smart',  '🎯 Seguir al sujeto'),
        ('center', '⬛ Recorte al centro'),
        ('padded', '🔲 Completo con fondo difuso'),
    ]

    AI_MODELS = [
        ('sora-2',     '✨ Sora 2 — ~$0.10/video (recomendado)'),
        ('sora-2-pro', '🏆 Sora 2 Pro — ~$0.20/video, máxima calidad'),
        ('fal-ai/kling-video/o3/standard/image-to-video', '⚡ Kling O3 Standard (fal.ai)'),
        ('fal-ai/kling-video/o3/pro/image-to-video',      '⚡ Kling O3 Pro (fal.ai)'),
        ('fal-ai/minimax/video-01/image-to-video',         '⚡ Minimax Video-01 (fal.ai)'),
    ]

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='projects')
    name         = models.CharField('Nombre', max_length=200)
    status       = models.CharField(max_length=20, choices=STATUS, default='draft')
    prompt       = models.TextField('Prompt', blank=True)
    transition   = models.CharField('Transición', max_length=20, choices=TRANSITIONS, default='crossfade')
    ai_model     = models.CharField('Modelo IA', max_length=100, default='sora-2')
    source_type  = models.CharField('Origen', max_length=10, choices=SOURCE_TYPES, default='photos')
    source_video = models.FileField('Video de origen', upload_to='sources/', blank=True, null=True)
    reframe_mode = models.CharField('Reencuadre', max_length=10, choices=REFRAME_MODES, default='smart')
    subtitles    = models.BooleanField('Subtítulos automáticos', default=True)
    srt_file     = models.FileField('Subtítulos .srt', upload_to='srt/', blank=True, null=True)
    music_choice = models.CharField('Música', max_length=100, choices=MUSIC_CHOICES, default='cinematic')
    music_file   = models.FileField('Mi música', upload_to=music_path, blank=True, null=True)
    task_id      = models.CharField(max_length=255, blank=True)
    progress     = models.PositiveSmallIntegerField(default=0)
    progress_msg = models.CharField(max_length=500, blank=True)
    error_msg    = models.TextField(blank=True)
    video_file   = models.FileField('Video', upload_to='videos/', blank=True, null=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.get_status_display()})'

    @property
    def image_count(self):
        return self.images.count()

    @property
    def clips_done(self):
        return self.images.filter(clip_status='done').count()

    def get_video_url(self):
        return self.video_file.url if self.video_file else None

    def get_effective_prompt(self):
        from django.conf import settings
        return self.prompt.strip() or getattr(settings, 'DEFAULT_VIDEO_PROMPT', '')

    def get_effective_model(self):
        from django.conf import settings
        return self.ai_model.strip() or getattr(settings, 'AI_VIDEO_MODEL', 'sora-2')


class PropertyImage(models.Model):
    CLIP_STATUS = [
        ('pending',    'Pendiente'),
        ('generating', 'Generando'),
        ('done',       'Listo'),
        ('error',      'Error'),
    ]
    project     = models.ForeignKey(VideoProject, on_delete=models.CASCADE, related_name='images')
    image       = models.ImageField('Imagen', upload_to=img_path)
    order       = models.PositiveIntegerField(default=0)
    clip_status = models.CharField(max_length=20, choices=CLIP_STATUS, default='pending')
    clip_file   = models.FileField('Clip', upload_to='clips/', blank=True, null=True)
    clip_error  = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'uploaded_at']
