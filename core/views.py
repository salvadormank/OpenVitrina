import json, os
from pathlib import Path
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib import messages
from django.conf import settings
from .models import VideoProject, PropertyImage
from .tasks import generate_reel


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('index')
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        return redirect(request.GET.get('next', '/'))
    return render(request, 'core/login.html', {'form': form})


def register_view(request):
    if request.user.is_authenticated:
        return redirect('index')
    form = UserCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect('index')
    return render(request, 'core/register.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


# ── Index ─────────────────────────────────────────────────────────────────────

@login_required
def index(request):
    projects = VideoProject.objects.filter(owner=request.user)
    return render(request, 'core/index.html', {'projects': projects})


# ── Nuevo proyecto ────────────────────────────────────────────────────────────

@login_required
def new_project(request):
    if request.method == 'POST':
        images = request.FILES.getlist('images')
        if not images:
            messages.error(request, 'Sube al menos una imagen.')
            return redirect('new_project')

        project = VideoProject.objects.create(
            owner        = request.user,
            name         = request.POST.get('name', 'Mi Propiedad'),
            prompt       = request.POST.get('prompt', '').strip(),
            transition   = request.POST.get('transition', 'crossfade'),
            ai_model     = request.POST.get('ai_model', 'sora-2'),
            music_choice = request.POST.get('music_choice', 'cinematic'),
        )
        if project.music_choice == 'upload' and 'music_file' in request.FILES:
            project.music_file = request.FILES['music_file']
            project.save(update_fields=['music_file'])

        for i, f in enumerate(images):
            PropertyImage.objects.create(project=project, image=f, order=i)

        return redirect('project_detail', pk=project.pk)

    context = {
        'default_prompt': getattr(settings, 'DEFAULT_VIDEO_PROMPT', ''),
        'transitions':    VideoProject.TRANSITIONS,
        'music_choices':  VideoProject.MUSIC_CHOICES,
    }
    return render(request, 'core/new_project.html', context)


# ── Detalle ───────────────────────────────────────────────────────────────────

@login_required
def project_detail(request, pk):
    project = get_object_or_404(VideoProject, pk=pk, owner=request.user)
    return render(request, 'core/project_detail.html', {'project': project})


# ── Generar ───────────────────────────────────────────────────────────────────

@login_required
@require_POST
def generate(request, pk):
    project = get_object_or_404(VideoProject, pk=pk, owner=request.user)
    if project.status in ('generating', 'concat', 'queued'):
        return JsonResponse({'status': 'already_running'})

    project.images.all().update(clip_status='pending')
    project.status    = 'queued'
    project.progress  = 0
    project.error_msg = ''
    project.video_file = None
    project.save(update_fields=['status', 'progress', 'error_msg', 'video_file'])

    task = generate_reel.delay(str(project.pk))
    project.task_id = task.id
    project.save(update_fields=['task_id'])

    return JsonResponse({'status': 'queued', 'task_id': task.id})


# ── Estado ────────────────────────────────────────────────────────────────────

@login_required
def status(request, pk):
    project = get_object_or_404(VideoProject, pk=pk, owner=request.user)
    clips   = list(project.images.values('id', 'order', 'clip_status', 'clip_error'))
    return JsonResponse({
        'status':       project.status,
        'progress':     project.progress,
        'progress_msg': project.progress_msg,
        'video_url':    project.get_video_url(),
        'error_msg':    project.error_msg,
        'clips':        clips,
        'clips_done':   project.clips_done,
        'clips_total':  project.image_count,
    })


# ── Descarga ──────────────────────────────────────────────────────────────────

@login_required
def download(request, pk):
    project = get_object_or_404(VideoProject, pk=pk, owner=request.user)
    if not project.video_file:
        raise Http404
    path = project.video_file.path
    if not os.path.exists(path):
        raise Http404
    name = f'{project.name.replace(" ", "_")}_reel.mp4'
    resp = FileResponse(open(path, 'rb'), content_type='video/mp4')
    resp['Content-Disposition'] = f'attachment; filename="{name}"'
    return resp


# ── Eliminar ──────────────────────────────────────────────────────────────────

@login_required
@require_POST
def delete_project(request, pk):
    project = get_object_or_404(VideoProject, pk=pk, owner=request.user)
    project.delete()
    messages.success(request, 'Proyecto eliminado.')
    return redirect('index')


# ── Reordenar ─────────────────────────────────────────────────────────────────

@login_required
@require_POST
def reorder_images(request, pk):
    project = get_object_or_404(VideoProject, pk=pk, owner=request.user)
    try:
        order = json.loads(request.body).get('order', [])
        for pos, img_id in enumerate(order):
            PropertyImage.objects.filter(pk=img_id, project=project).update(order=pos)
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)
