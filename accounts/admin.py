from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display
from unfold.enums import ActionVariant
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from finaltest.admin_helpers import render_submission_answers
from finaltest.models import FinalTestSubmission
from onboarding.models import ModuleAttempt, ModuleProgress, StepProgress

from .models import Invitation, Student

STUDENT_LABELS = {
    Student.Status.IN_PROGRESS: 'default',
    Student.Status.PENDING_REVIEW: 'info',
    Student.Status.APPROVED: 'success',
    Student.Status.NEEDS_REWORK: 'warning',
    Student.Status.REJECTED: 'danger',
}
INVITATION_LABELS = {
    Invitation.Status.PENDING: 'info',
    Invitation.Status.USED: 'success',
    Invitation.Status.REVOKED: 'danger',
}

COPY_JS = (
    "var b=this,u=location.origin+b.dataset.path;"
    "var ok=function(){b.textContent='Скопировано ✓'};"
    "if(navigator.clipboard){navigator.clipboard.writeText(u).then(ok,function(){prompt('Скопируй ссылку:',u)})}"
    "else{prompt('Скопируй ссылку:',u)}"
)
COPY_BUTTON_STYLE = (
    'cursor:pointer;border:1px solid #2663eb;color:#2663eb;background:transparent;'
    'border-radius:6px;padding:3px 10px;font-size:12px;font-weight:600;white-space:nowrap'
)


@admin.register(Invitation)
class InvitationAdmin(ModelAdmin):
    list_display = ('full_name', 'status_label', 'created_at', 'used_at', 'copy_link')
    list_filter = ('status',)
    search_fields = ('full_name',)
    readonly_fields = ('token', 'status', 'created_by', 'created_at', 'used_at', 'invite_link')
    fields = ('full_name', 'invite_link', 'status', 'created_by', 'created_at', 'used_at')
    actions = ['revoke_invitations']

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def _path(self, obj):
        try:
            return obj.get_absolute_url()
        except NoReverseMatch:
            return None

    @display(description='Статус', ordering='status', label=INVITATION_LABELS)
    def status_label(self, obj):
        return obj.status, obj.get_status_display()

    @display(description='Ссылка')
    def copy_link(self, obj):
        path = self._path(obj)
        if obj.status != Invitation.Status.PENDING or not path:
            return '—'
        return format_html(
            '<button type="button" style="{}" data-path="{}" onclick="{}">Скопировать ссылку</button>',
            COPY_BUTTON_STYLE, path, COPY_JS,
        )

    @display(description='Ссылка-приглашение (отправь её стажёру)')
    def invite_link(self, obj):
        if not obj.pk:
            return 'Ссылка появится после сохранения'
        path = self._path(obj)
        if not path:
            return '—'
        if obj.status == Invitation.Status.USED:
            return 'Стажёр уже зарегистрировался по этой ссылке'
        if obj.status == Invitation.Status.REVOKED:
            return 'Приглашение отозвано — ссылка не работает'
        return format_html(
            '<a href="{0}" target="_blank" class="invite-abs" style="color:#2663eb;word-break:break-all">{0}</a> &nbsp;'
            '<button type="button" style="{2}" data-path="{0}" onclick="{1}">Скопировать ссылку</button>'
            '<script>(function(){{var a=document.currentScript.parentNode.querySelector(".invite-abs");'
            'a.textContent=location.origin+a.getAttribute("href")}})()</script>',
            path, COPY_JS, COPY_BUTTON_STYLE,
        )

    @action(description='Отозвать выбранные приглашения (ссылка перестанет работать)')
    def revoke_invitations(self, request, queryset):
        updated = queryset.filter(status=Invitation.Status.PENDING).update(status=Invitation.Status.REVOKED)
        self.message_user(request, f'Отозвано приглашений: {updated}', messages.SUCCESS)


class ModuleProgressInline(TabularInline):
    model = ModuleProgress
    extra = 0
    can_delete = False
    fields = ('module', 'completed_at')
    readonly_fields = fields
    verbose_name_plural = 'Пройденные модули'

    def has_add_permission(self, request, obj=None):
        return False


class StepProgressInline(TabularInline):
    model = StepProgress
    extra = 0
    can_delete = False
    fields = ('step', 'is_done', 'note', 'done_at')
    readonly_fields = fields
    ordering = ('step__module__order', 'step__order')
    verbose_name_plural = 'Шаги обучения: что отметил ученик и что написал в заметках'

    def has_add_permission(self, request, obj=None):
        return False


class ModuleAttemptInline(TabularInline):
    model = ModuleAttempt
    extra = 0
    can_delete = False
    fields = ('module', 'attempt_number', 'is_passed', 'correct_count', 'total_count', 'created_at')
    readonly_fields = fields
    verbose_name_plural = 'Попытки прохождения модулей'

    def has_add_permission(self, request, obj=None):
        return False


class FinalTestSubmissionInline(TabularInline):
    model = FinalTestSubmission
    extra = 0
    can_delete = False
    fields = ('attempt_number', 'started_at', 'submitted_at', 'mcq_score_percent')
    readonly_fields = fields
    verbose_name_plural = 'Все попытки финального теста (по ссылке «Изменить» — комментарии к ответам)'
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Student)
class StudentAdmin(ModelAdmin):
    list_display = (
        'full_name', 'status_label', 'current_module_display', 'progress_bar',
        'failed_attempts', 'final_attempts', 'final_score', 'started_at',
    )
    list_filter = ('status',)
    list_fullwidth = True
    warn_unsaved_form = True
    search_fields = ('user__first_name', 'user__last_name', 'user__username')
    actions = ['mark_approved', 'mark_needs_rework', 'mark_rejected']
    actions_detail = ['approve_detail', 'rework_detail', 'reject_detail']
    readonly_fields = ('user', 'invitation', 'started_at', 'progress_percent_display', 'final_test_answers')
    fieldsets = (
        (None, {'fields': ('user', 'invitation', 'started_at', 'progress_percent_display')}),
        ('Ответы на финальный тест (последняя отправленная попытка)', {'fields': ('final_test_answers',)}),
        ('Решение', {'fields': ('status', 'final_score', 'admin_note')}),
    )
    inlines = [ModuleProgressInline, StepProgressInline, ModuleAttemptInline, FinalTestSubmissionInline]

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related('user')
            .annotate(
                _failed_attempts=Count(
                    'module_attempts', filter=Q(module_attempts__is_passed=False), distinct=True,
                ),
                _final_attempts=Count(
                    'final_submissions', filter=Q(final_submissions__submitted_at__isnull=False), distinct=True,
                ),
            )
        )

    @display(description='Ученик', ordering='user__first_name')
    def full_name(self, obj):
        return str(obj)

    @display(description='Статус', ordering='status', label=STUDENT_LABELS)
    def status_label(self, obj):
        return obj.status, obj.get_status_display()

    @display(description='Текущий модуль')
    def current_module_display(self, obj):
        module = obj.current_module
        return str(module) if module else 'Курс пройден'

    @display(description='Прогресс')
    def progress_bar(self, obj):
        percent = obj.progress_percent
        return format_html(
            '<div style="min-width:150px">{}</div>',
            render_to_string(
                'unfold/components/progress.html', {'value': percent, 'description': f'{percent}%'},
            ),
        )

    @display(description='Ошибок в модулях', ordering='_failed_attempts')
    def failed_attempts(self, obj):
        return obj._failed_attempts

    @display(description='Сдач теста', ordering='_final_attempts')
    def final_attempts(self, obj):
        return obj._final_attempts

    @display(description='Прогресс')
    def progress_percent_display(self, obj):
        return f'{obj.progress_percent}%'

    @display(description='Ответы')
    def final_test_answers(self, obj):
        submission = obj.final_submissions.filter(submitted_at__isnull=False).order_by('-submitted_at').first()
        return render_submission_answers(submission)

    def _set_status(self, request, queryset, status):
        updated = queryset.update(status=status)
        label = Student.Status(status).label
        self.message_user(request, f'Статус «{label}» выставлен: {updated}', messages.SUCCESS)

    @action(description='Статус → Допущен')
    def mark_approved(self, request, queryset):
        self._set_status(request, queryset, Student.Status.APPROVED)

    @action(description='Статус → На доработку (откроет пересдачу теста)')
    def mark_needs_rework(self, request, queryset):
        self._set_status(request, queryset, Student.Status.NEEDS_REWORK)

    @action(description='Статус → Отказ')
    def mark_rejected(self, request, queryset):
        self._set_status(request, queryset, Student.Status.REJECTED)

    def _decide(self, request, object_id, status):
        student = get_object_or_404(Student, pk=object_id)
        student.status = status
        student.save(update_fields=['status'])
        messages.success(request, f'{student}: статус «{Student.Status(status).label}»')
        return redirect(reverse('admin:accounts_student_change', args=[object_id]))

    @action(description='Допустить', icon='check_circle', variant=ActionVariant.SUCCESS, url_path='approve')
    def approve_detail(self, request, object_id):
        return self._decide(request, object_id, Student.Status.APPROVED)

    @action(description='На доработку', icon='replay', variant=ActionVariant.WARNING, url_path='rework')
    def rework_detail(self, request, object_id):
        return self._decide(request, object_id, Student.Status.NEEDS_REWORK)

    @action(description='Отказ', icon='cancel', variant=ActionVariant.DANGER, url_path='reject')
    def reject_detail(self, request, object_id):
        return self._decide(request, object_id, Student.Status.REJECTED)


admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass
