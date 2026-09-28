import bleach
import markdown
from django.db import models
from django.utils.translation import gettext as _

from accounts.models import Student
from core.i18n import localized
from core.ordering import next_order

MARKDOWN_ALLOWED_TAGS = (bleach.sanitizer.ALLOWED_TAGS | {
    'p', 'h1', 'h2', 'h3', 'h4', 'pre', 'span', 'br', 'img', 'hr',
})
MARKDOWN_ALLOWED_ATTRS = {**bleach.sanitizer.ALLOWED_ATTRIBUTES, 'img': ['src', 'alt']}


def render_markdown(text):
    raw_html = markdown.markdown(text or '', extensions=['extra'])
    return bleach.clean(raw_html, tags=MARKDOWN_ALLOWED_TAGS, attributes=MARKDOWN_ALLOWED_ATTRS)


class Module(models.Model):
    title = models.CharField('Название модуля', max_length=200)
    order = models.PositiveSmallIntegerField(
        'Порядок', unique=True, default=0, help_text='Оставь 0 — модуль встанет следом за последним.',
    )
    title_uz = models.CharField('Название (узб.)', max_length=200, blank=True)
    is_published = models.BooleanField('Опубликован', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order']
        verbose_name = 'Модуль'
        verbose_name_plural = 'Модули'

    def __str__(self):
        return f'{self.order}. {self.title}'

    def save(self, *args, **kwargs):
        if not self.order:
            self.order = next_order(Module.objects.all())
        super().save(*args, **kwargs)

    @property
    def l_title(self):
        return localized(self.title, self.title_uz)



class ModuleQuestion(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='questions')
    text = models.CharField('Вопрос', max_length=500)
    text_uz = models.CharField('Вопрос (узб.)', max_length=500, blank=True)
    order = models.PositiveSmallIntegerField('Порядок', default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Контрольный вопрос'
        verbose_name_plural = 'Контрольные вопросы'

    def __str__(self):
        return self.text

    def save(self, *args, **kwargs):
        if not self.order:
            self.order = next_order(ModuleQuestion.objects.filter(module_id=self.module_id))
        super().save(*args, **kwargs)

    @property
    def l_text(self):
        return localized(self.text, self.text_uz)


class ModuleAnswerOption(models.Model):
    question = models.ForeignKey(ModuleQuestion, on_delete=models.CASCADE, related_name='options')
    text = models.CharField('Вариант ответа', max_length=300)
    text_uz = models.CharField('Вариант ответа (узб.)', max_length=300, blank=True)
    is_correct = models.BooleanField('Правильный', default=False)

    class Meta:
        verbose_name = 'Вариант ответа'
        verbose_name_plural = 'Варианты ответа'

    def __str__(self):
        return self.text

    @property
    def l_text(self):
        return localized(self.text, self.text_uz)


class ModuleProgress(models.Model):
    """Отметка, что ученик прошёл модуль (все контрольные вопросы отвечены верно)."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='module_progress', verbose_name='Ученик')
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='progress_records', verbose_name='Модуль')
    completed_at = models.DateTimeField('Завершён', auto_now_add=True)

    class Meta:
        unique_together = ('student', 'module')
        verbose_name = 'Прогресс по модулю'
        verbose_name_plural = 'Прогресс по модулям'

    def __str__(self):
        return f'{self.student} — {self.module}'


class ModuleAttempt(models.Model):
    """Одна попытка ответить на контрольные вопросы модуля. Хранится для подсчёта попыток."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='module_attempts', verbose_name='Ученик')
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='attempts', verbose_name='Модуль')
    attempt_number = models.PositiveSmallIntegerField('Попытка №')
    is_passed = models.BooleanField('Пройдена', default=False)
    correct_count = models.PositiveSmallIntegerField('Верных ответов', default=0)
    total_count = models.PositiveSmallIntegerField('Всего вопросов', default=0)
    created_at = models.DateTimeField('Дата', auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Попытка прохождения модуля'
        verbose_name_plural = 'Попытки прохождения модулей'

    def __str__(self):
        return f'{self.student} — {self.module} — попытка {self.attempt_number}'


class ModuleAttemptAnswer(models.Model):
    attempt = models.ForeignKey(ModuleAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(ModuleQuestion, on_delete=models.CASCADE)
    selected_option = models.ForeignKey(ModuleAnswerOption, on_delete=models.CASCADE)
    is_correct = models.BooleanField()

    class Meta:
        verbose_name = 'Ответ в попытке'
        verbose_name_plural = 'Ответы в попытках'


class ModuleDraft(models.Model):
    """Черновик ответов на контрольные вопросы модуля: сохраняется автоматически при каждом выборе."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='module_drafts', verbose_name='Ученик')
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='drafts', verbose_name='Модуль')
    answers = models.JSONField('Выбранные ответы {id вопроса: id варианта}', default=dict)
    updated_at = models.DateTimeField('Обновлён', auto_now=True)

    class Meta:
        unique_together = ('student', 'module')
        verbose_name = 'Черновик ответов на модуль'
        verbose_name_plural = 'Черновики ответов на модули'

    def __str__(self):
        return f'{self.student} — {self.module}'


class ModuleStep(models.Model):
    """Шаг обучения внутри модуля: видео, материал, практическое задание или ссылка. Ученик отмечает его выполненным."""

    class Kind(models.TextChoices):
        VIDEO = 'video', 'Видео'
        TEXT = 'text', 'Материал (текст)'
        ACTION = 'action', 'Практическое задание'
        RESOURCE = 'resource', 'Ссылка / файл'

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='steps', verbose_name='Модуль')
    order = models.PositiveSmallIntegerField('Порядок', default=0)
    kind = models.CharField('Тип шага', max_length=10, choices=Kind.choices, default=Kind.TEXT)
    title = models.CharField('Заголовок', max_length=200)
    body = models.TextField(
        'Текст / инструкция (markdown)', blank=True,
        help_text='Для материала — сам текст; для практического задания — что именно нужно сделать.',
    )
    youtube_id = models.CharField(
        'YouTube ID', max_length=32, blank=True, help_text='Только для видео: ID из ссылки youtube.com/watch?v=XXXX',
    )
    url = models.URLField('Ссылка', blank=True, help_text='Только для «Ссылка / файл»')
    is_required = models.BooleanField(
        'Обязательный', default=True, help_text='Пока обязательные шаги не выполнены, тест модуля закрыт.',
    )
    requires_note = models.BooleanField(
        'Нужна заметка', default=False,
        help_text='Только для практического задания: без короткой заметки ученика отметить шаг нельзя.',
    )
    title_uz = models.CharField('Заголовок (узб.)', max_length=200, blank=True)
    body_uz = models.TextField('Текст (узб., markdown)', blank=True)
    youtube_id_uz = models.CharField(
        'YouTube ID (узб.)', max_length=32, blank=True, help_text='Если пусто — покажем русское видео',
    )

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Шаг обучения'
        verbose_name_plural = 'Шаги обучения'

    def __str__(self):
        return f'{self.module.order}.{self.order} {self.title}'

    def save(self, *args, **kwargs):
        if not self.order:
            self.order = next_order(ModuleStep.objects.filter(module_id=self.module_id))
        super().save(*args, **kwargs)

    @property
    def l_title(self):
        return localized(self.title, self.title_uz)

    @property
    def l_body_html(self):
        return render_markdown(localized(self.body, self.body_uz))

    @property
    def l_youtube_id(self):
        return localized(self.youtube_id, self.youtube_id_uz)

    @property
    def needs_note(self):
        """Заметка обязательна только у практического задания (у остальных шагов нет поля для неё)."""
        return self.requires_note and self.kind == self.Kind.ACTION

    @property
    def kind_label(self):
        return {
            self.Kind.VIDEO: _('Видео'),
            self.Kind.TEXT: _('Материал'),
            self.Kind.ACTION: _('Практика'),
            self.Kind.RESOURCE: _('Ссылка'),
        }[self.kind]

    @property
    def todo_label(self):
        return {
            self.Kind.VIDEO: _('Отметить как просмотренное'),
            self.Kind.TEXT: _('Отметить как прочитанное'),
            self.Kind.ACTION: _('Отметить как выполненное'),
            self.Kind.RESOURCE: _('Отметить как изученное'),
        }[self.kind]

    @property
    def done_label(self):
        return {
            self.Kind.VIDEO: _('Просмотрено'),
            self.Kind.TEXT: _('Прочитано'),
            self.Kind.ACTION: _('Выполнено'),
            self.Kind.RESOURCE: _('Изучено'),
        }[self.kind]


class StepProgress(models.Model):
    """Отметка ученика, что шаг выполнен, и его короткая заметка («что понял / что сделал»)."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='step_progress', verbose_name='Ученик')
    step = models.ForeignKey(ModuleStep, on_delete=models.CASCADE, related_name='progress_records', verbose_name='Шаг')
    is_done = models.BooleanField('Выполнен', default=False)
    note = models.TextField('Заметка ученика', blank=True)
    done_at = models.DateTimeField('Когда выполнен', null=True, blank=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        unique_together = ('student', 'step')
        verbose_name = 'Прогресс по шагу'
        verbose_name_plural = 'Прогресс по шагам'

    def __str__(self):
        return f'{self.student} — {self.step}'
