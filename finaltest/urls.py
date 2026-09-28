from django.urls import path

from . import views

app_name = 'finaltest'

urlpatterns = [
    path('final-test/', views.take_test, name='take'),
    path('final-test/draft/', views.save_draft, name='draft'),
    path('final-test/submitted/', views.submitted, name='submitted'),
]
