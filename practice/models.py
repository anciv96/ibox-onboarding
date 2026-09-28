from django.db import models
from django.utils.translation import gettext_lazy as _

from accounts.models import Student
from core.i18n import localized


class PracticeQuestion(models.Model):
    """Вопрос свободного лобби «Тренировка»: не оценивается руководителем, стажёр играет по своей инициативе."""

    class Category(models.TextChoices):
        CASES = 'cases', _('Кейсы: бизнес → решение')
        ODD = 'odd', _('Нестандартные бизнесы')
        ROUTE = 'route', _('Куда идти?')
        TARIFF = 'tariff', _('Тарифы и продукты')
        MYTH = 'myth', _('Правда или миф')
        MONEY = 'money', _('Деньги и цифры')

    category = models.CharField('Игра', max_length=10, choices=Category.choices)
    prompt = models.TextField('Вопрос / ситуация')
    prompt_uz = models.TextField('Вопрос (узб.)', blank=True)
    explanation = models.TextField('Разбор (показывается после ответа)', blank=True)
    explanation_uz = models.TextField('Разбор (узб.)', blank=True)
    is_published = models.BooleanField('Показывать стажёрам', default=True)

    class Meta:
        ordering = ['category', 'id']
        verbose_name = 'Вопрос тренировки'
        verbose_name_plural = 'Вопросы тренировки'

    def __str__(self):
        return self.prompt[:60]

    @property
    def l_prompt(self):
        return localized(self.prompt, self.prompt_uz)

    @property
    def l_explanation(self):
        return localized(self.explanation, self.explanation_uz)


class PracticeOption(models.Model):
    question = models.ForeignKey(PracticeQuestion, on_delete=models.CASCADE, related_name='options')
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


class PracticeAnswer(models.Model):
    """Ответ в тренировке — нужен только ученику: личная статистика и подбор ещё не виденных вопросов."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='practice_answers')
    question = models.ForeignKey(PracticeQuestion, on_delete=models.CASCADE, related_name='answers')
    is_correct = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Ответ в тренировке'
        verbose_name_plural = 'Ответы в тренировке'
