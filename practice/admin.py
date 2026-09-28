from django.contrib import admin
from unfold.admin import ModelAdmin, StackedInline, TabularInline

from .models import PracticeOption, PracticeQuestion


class PracticeOptionInline(TabularInline):
    model = PracticeOption
    extra = 2


@admin.register(PracticeQuestion)
class PracticeQuestionAdmin(ModelAdmin):
    list_display = ('prompt_short', 'category', 'is_published')
    list_display_links = ('prompt_short',)
    list_filter = ('category', 'is_published')
    search_fields = ('prompt',)
    inlines = [PracticeOptionInline]
    fieldsets = (
        (None, {'fields': ('category', 'prompt', 'explanation', 'is_published')}),
        ('Узбекский перевод', {'fields': ('prompt_uz', 'explanation_uz'), 'classes': ('collapse',)}),
    )

    @admin.display(description='Вопрос')
    def prompt_short(self, obj):
        return obj.prompt[:80]
