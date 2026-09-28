import random
import uuid

from django.utils.translation import gettext_lazy as _

from .models import PracticeAnswer, PracticeOption, PracticeQuestion

ROUND_SIZE = 10

CATEGORY_HINTS = {
    'cases': _('Бизнес с задачей — найди решение в iBox, не зная подсказки.'),
    'odd': _('Аренда, салоны, сервисы, производство: подходит ли iBox и как обойти ограничение.'),
    'route': _('Ситуация из работы — в какой раздел, документ или отчёт идти.'),
    'tariff': _('Подбери тариф или пойми, что клиенту нужен другой продукт.'),
    'myth': _('Быстрая игра: утверждение — правда или миф?'),
    'money': _('Деньги, долги, прибыль: что показать клиенту и в каком порядке.'),
}


def pool(category=None):
    questions = PracticeQuestion.objects.filter(is_published=True)
    if category:
        questions = questions.filter(category=category)
    return questions


def pick_round(student, category=None, size=ROUND_SIZE):
    """Сначала ещё не виденные вопросы, затем те, где ошибались, затем остальные — всё в случайном порядке."""
    ids = list(pool(category).values_list('id', flat=True))
    history = {}
    for question_id, is_correct in PracticeAnswer.objects.filter(student=student, question_id__in=ids).order_by('id').values_list('question_id', 'is_correct'):
        history[question_id] = is_correct  # остаётся результат последнего ответа
    unseen = [i for i in ids if i not in history]
    wrong = [i for i in ids if history.get(i) is False]
    right = [i for i in ids if history.get(i) is True]
    chosen = []
    for bucket in (unseen, wrong, right):
        random.shuffle(bucket)
        chosen += bucket[:size - len(chosen)]
    random.shuffle(chosen)
    return chosen


def new_round(student, category=None):
    ids = pick_round(student, category)
    if not ids:
        return None
    return {'token': uuid.uuid4().hex[:12], 'ids': ids, 'i': 0, 'results': [], 'pending': None, 'category': category or ''}


def shuffled_options(token, question):
    options = list(question.options.all())
    random.Random(f'{token}-{question.pk}').shuffle(options)
    return options


def record_answer(student, question, option_id):
    """Возвращает (option, is_correct) или None, если вариант не принадлежит вопросу."""
    option = PracticeOption.objects.filter(pk=option_id, question=question).first()
    if option is None:
        return None
    PracticeAnswer.objects.create(student=student, question=question, is_correct=option.is_correct)
    return option, option.is_correct


def stats(student):
    """Личная статистика: сколько ответов, точность, сколько вопросов освоено (последний ответ верный) и по играм."""
    published = {q.id: q.category for q in pool()}
    last = {}
    total = correct = 0
    for question_id, is_correct in PracticeAnswer.objects.filter(student=student).order_by('id').values_list('question_id', 'is_correct'):
        total += 1
        correct += is_correct
        last[question_id] = is_correct
    mastered = {i for i, ok in last.items() if ok and i in published}
    categories = []
    for value, label in PracticeQuestion.Category.choices:
        ids = [i for i, c in published.items() if c == value]
        if ids:
            categories.append({
                'key': value, 'label': label, 'hint': CATEGORY_HINTS.get(value, ''), 'total': len(ids),
                'mastered': sum(1 for i in ids if i in mastered),
            })
    return {
        'answered': total,
        'accuracy': round(100 * correct / total) if total else None,
        'mastered': len(mastered),
        'pool': len(published),
        'categories': categories,
    }
