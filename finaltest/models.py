from django.db import models

from accounts.models import Student
from core.i18n import localized
from core.ordering import next_order


class FinalTestItem(models.Model):
    class Type(models.TextChoices):
        MCQ = 'mcq', 'Вопрос с вариантами'
        OPEN = 'open', 'Открытый вопрос'
        CASE = 'case', 'Кейс с возражением'

    type = models.CharField('Тип', max_length=10, choices=Type.choices)
    prompt = models.TextField('Текст вопроса / фраза клиента')
    prompt_uz = models.TextField('Текст вопроса (узб.)', blank=True)
    order = models.PositiveSmallIntegerField('Порядок', default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Элемент финального теста'
        verbose_name_plural = 'Элементы финального теста'

    def __str__(self):
        return f'[{self.get_type_display()}] {self.prompt[:50]}'

    def save(self, *args, **kwargs):
        if not self.order:
            self.order = next_order(FinalTestItem.objects.all())
        super().save(*args, **kwargs)

    @property
    def l_prompt(self):
        return localized(self.prompt, self.prompt_uz)


class FinalTestOption(models.Model):
    item = models.ForeignKey(FinalTestItem, on_delete=models.CASCADE, related_name='options')
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


class FinalTestSubmission(models.Model):
    """
    Одна попытка прохождения финального теста.
    Пересдачи разрешены (когда статус ученика "на доработку") — хранятся ВСЕ попытки, не только последняя.
    """

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='final_submissions', verbose_name='Ученик')
    attempt_number = models.PositiveSmallIntegerField('Попытка №')
    started_at = models.DateTimeField('Начата', auto_now_add=True)
    submitted_at = models.DateTimeField('Отправлена', null=True, blank=True)
    mcq_score_percent = models.PositiveSmallIntegerField('Вопросы с вариантами, %', null=True, blank=True)
    item_ids = models.JSONField('Вопросы этой попытки (в порядке показа)', default=list, blank=True)
    draft = models.JSONField('Черновик ответов {id вопроса: ответ}', default=dict, blank=True)
    draft_saved_at = models.DateTimeField('Черновик сохранён', null=True, blank=True)

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Попытка финального теста'
        verbose_name_plural = 'Попытки финального теста'

    def __str__(self):
        return f'{self.student} — попытка {self.attempt_number}'

    @property
    def is_submitted(self):
        return self.submitted_at is not None


class FinalTestAnswer(models.Model):
    submission = models.ForeignKey(FinalTestSubmission, on_delete=models.CASCADE, related_name='answers', verbose_name='Попытка')
    item = models.ForeignKey(FinalTestItem, on_delete=models.CASCADE, verbose_name='Вопрос')
    selected_option = models.ForeignKey(
        FinalTestOption, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Выбранный вариант',
    )
    text_answer = models.TextField('Письменный ответ', blank=True)
    is_correct = models.BooleanField('Верно', null=True, blank=True)  # только для mcq
    ai_score = models.PositiveSmallIntegerField('AI-оценка (заготовка на будущее)', null=True, blank=True)
    admin_comment = models.TextField('Комментарий админа', blank=True)

    class Meta:
        verbose_name = 'Ответ в финальном тесте'
        verbose_name_plural = 'Ответы в финальном тесте'

    def __str__(self):
        return f'{self.submission} — {self.item}'
