from django.urls import path
from . import views

urlpatterns = [
    path('',                       views.index,          name='index'),
    path('login/',                 views.login_view,     name='login'),
    path('registro/',              views.register_view,  name='register'),
    path('logout/',                views.logout_view,    name='logout'),
    path('nuevo/',                 views.new_project,    name='new_project'),
    path('p/<uuid:pk>/',           views.project_detail, name='project_detail'),
    path('p/<uuid:pk>/generar/',   views.generate,       name='generate'),
    path('p/<uuid:pk>/estado/',    views.status,         name='status'),
    path('p/<uuid:pk>/descargar/', views.download,       name='download'),
    path('p/<uuid:pk>/eliminar/',  views.delete_project, name='delete_project'),
    path('p/<uuid:pk>/reordenar/', views.reorder_images, name='reorder_images'),
]
