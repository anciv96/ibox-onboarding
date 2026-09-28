import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse


class Invitation(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает регистрации'
        USED = 'used', 'Использовано'
        REVOKED = 'revoked', 'Отозвано'

    token = models.UUIDField('Токен', default=uuid.uuid4, editable=False, unique=True)
    full_name = models.CharField('Имя ученика', max_length=150)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='invitations_created', verbose_name='Создал',
    )
    status = models.CharField('Статус', max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    used_at = models.DateTimeField('Использовано', null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Приглашение'
        verbose_name_plural = 'Приглашения'

    def __str__(self):
        return f'{self.full_name} ({self.get_status_display()})'

    def get_absolute_url(self):
        return reverse('accounts:register', kwargs={'token': str(self.token)})


class Student(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = 'in_progress', 'Проходит обучение'
        PENDING_REVIEW = 'pending_review', 'На проверке'
        APPROVED = 'approved', 'Допущен'
        NEEDS_REWORK = 'needs_rework', 'На доработку'
        REJECTED = 'rejected', 'Отказ'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='student_profile',
        verbose_name='Пользователь',
    )
    invitation = models.OneToOneField(
        Invitation, on_delete=models.SET_NULL, null=True, related_name='student',
        verbose_name='Приглашение',
    )
    status = models.CharField('Статус', max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    started_at = models.DateTimeField('Дата старта', auto_now_add=True)
    admin_note = models.TextField('Заметка админа', blank=True)
    final_score = models.PositiveSmallIntegerField('Итоговый балл', null=True, blank=True)

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Ученик'
        verbose_name_plural = 'Ученики'

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    @property
    def progress_percent(self):
        from onboarding.progress import overall_progress

        return overall_progress(self)['percent']

    @property
    def current_module(self):
        from onboarding.models import Module

        completed_ids = self.module_progress.values_list('module_id', flat=True)
        return (
            Module.objects.filter(is_published=True)
            .exclude(id__in=completed_ids)
            .order_by('order')
            .first()
        )
