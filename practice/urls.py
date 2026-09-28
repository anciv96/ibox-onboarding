from django.urls import path

from . import views

app_name = 'practice'

urlpatterns = [
    path('practice/', views.lobby, name='lobby'),
    path('practice/start/', views.start, name='start'),
    path('practice/play/', views.play, name='play'),
]
