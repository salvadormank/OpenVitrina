from django.contrib import admin
from .models import VideoProject, PropertyImage

class ImgInline(admin.TabularInline):
    model  = PropertyImage
    extra  = 0
    fields = ['image', 'order', 'clip_status', 'clip_file']
    readonly_fields = ['clip_status', 'clip_file']

@admin.register(VideoProject)
class ProjectAdmin(admin.ModelAdmin):
    list_display    = ['name', 'owner', 'status', 'progress', 'image_count', 'created_at']
    list_filter     = ['status']
    readonly_fields = ['id', 'task_id', 'progress', 'created_at', 'updated_at']
    inlines         = [ImgInline]

@admin.register(PropertyImage)
class ImageAdmin(admin.ModelAdmin):
    list_display = ['project', 'order', 'clip_status', 'uploaded_at']
    list_filter  = ['clip_status']
