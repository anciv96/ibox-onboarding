from django.contrib import admin
from django.db.models import Count
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.decorators import display

from .models import Module, ModuleAnswerOption, ModuleQuestion, ModuleStep


class ModuleAnswerOptionInline(TabularInline):
    model = ModuleAnswerOption
    extra = 2


@admin.register(ModuleQuestion)
class ModuleQuestionAdmin(ModelAdmin):
    list_display = ('text', 'module', 'order')
    list_filter = ('module',)
    ordering = ('module', 'order')
    inlines = [ModuleAnswerOptionInline]


class ModuleStepInline(StackedInline):
    model = ModuleStep
    extra = 1
    ordering = ('order', 'id')
    ordering_field = 'order'  # порядок задаётся перетаскиванием, вручную номера вписывать не нужно
    hide_ordering_field = True
    verbose_name = 'Шаг обучения'
    verbose_name_plural = 'Шаги обучения — что ученик изучает и делает до теста (порядок меняется перетаскиванием)'
    fieldsets = (
        (None, {'fields': (
            'kind', 'title', 'body', ('youtube_id', 'url'), ('is_required', 'requires_note'), 'order',
        )}),
        ('Узбекская версия (необязательно — если пусто, покажем русскую)', {
            'fields': ('title_uz', 'body_uz', 'youtube_id_uz'),
            'classes': ['collapse'],
        }),
    )


class ModuleQuestionInline(StackedInline):
    model = ModuleQuestion
    extra = 1
    show_change_link = True
    ordering_field = 'order'
    hide_ordering_field = True
    fields = ('text', 'text_uz', 'order')
    verbose_name_plural = 'Контрольные вопросы теста модуля (варианты ответа — по ссылке «Изменить»)'


@admin.register(Module)
class ModuleAdmin(ModelAdmin):
    list_display = ('order', 'title', 'is_published', 'steps_count', 'questions_count')
    list_display_links = ('title',)
    list_editable = ('is_published',)
    ordering = ('order',)
    inlines = [ModuleStepInline, ModuleQuestionInline]
    fieldsets = (
        (None, {'fields': ('order', 'title', 'is_published')}),
        ('Узбекская версия (необязательно)', {'fields': ('title_uz',), 'classes': ['collapse']}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _steps=Count('steps', distinct=True), _questions=Count('questions', distinct=True),
        )

    @display(description='Шагов обучения', ordering='_steps')
    def steps_count(self, obj):
        return obj._steps

    @display(description='Вопросов теста', ordering='_questions')
    def questions_count(self, obj):
        return obj._questions
