from django.urls import path

from . import views

app_name = 'onboarding'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('modules/<int:pk>/', views.module_detail, name='module_detail'),
    path('modules/<int:pk>/quiz/', views.module_quiz, name='module_quiz'),
    path('modules/<int:pk>/draft/', views.module_draft, name='module_draft'),
    path('modules/<int:pk>/steps/<int:step_id>/', views.module_step, name='module_step'),
]
