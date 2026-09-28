from django import forms
from django.contrib import admin
from django.db import models
from django.template.defaultfilters import linebreaksbr
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin, StackedInline, TabularInline

from .models import FinalTestAnswer, FinalTestItem, FinalTestOption, FinalTestSubmission


class FinalTestOptionInline(TabularInline):
    model = FinalTestOption
    extra = 2


@admin.register(FinalTestItem)
class FinalTestItemAdmin(ModelAdmin):
    list_display = ('prompt_short', 'type', 'order')
    list_display_links = ('prompt_short',)
    ordering_field = 'order'  # порядок вопросов — перетаскиванием в списке
    hide_ordering_field = True
    list_filter = ('type',)
    ordering = ('order',)
    inlines = [FinalTestOptionInline]

    @admin.display(description='Текст')
    def prompt_short(self, obj):
        return obj.prompt[:80]


class FinalTestAnswerInline(StackedInline):
    model = FinalTestAnswer
    extra = 0
    can_delete = False
    fields = ('question_text', 'answer_text', 'ai_score', 'admin_comment')
    readonly_fields = ('question_text', 'answer_text')
    verbose_name = 'Ответ'
    verbose_name_plural = 'Ответы ученика'
    formfield_overrides = {
        models.TextField: {'widget': forms.Textarea(attrs={'rows': 3, 'style': 'width:90%'})},
    }

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('item', 'selected_option').order_by('item__order', 'item__id')

    @admin.display(description='Вопрос')
    def question_text(self, obj):
        return format_html('<b>[{}]</b> {}', obj.item.get_type_display(), obj.item.prompt)

    @admin.display(description='Ответ ученика')
    def answer_text(self, obj):
        if obj.item.type == FinalTestItem.Type.MCQ:
            if obj.selected_option is None:
                return mark_safe('<i>ответ не выбран</i>')
            return format_html('{} {}', '✅' if obj.is_correct else '❌', obj.selected_option.text)
        return linebreaksbr(obj.text_answer) if obj.text_answer else mark_safe('<i>пусто</i>')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(FinalTestSubmission)
class FinalTestSubmissionAdmin(ModelAdmin):
    list_display = ('student', 'attempt_number', 'started_at', 'submitted_at', 'mcq_score_percent')
    list_filter = ('submitted_at',)
    search_fields = ('student__user__first_name', 'student__user__last_name')
    readonly_fields = ('student', 'attempt_number', 'started_at', 'submitted_at', 'mcq_score_percent')
    exclude = ('draft', 'draft_saved_at')
    inlines = [FinalTestAnswerInline]

    def has_add_permission(self, request):
        return False
