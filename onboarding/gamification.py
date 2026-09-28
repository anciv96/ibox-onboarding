"""
Лёгкая игровая механика онбординга: опыт (XP), ранги, серия дней, достижения.

Ничего не хранится отдельно — всё считается из уже существующих данных (отметки шагов, попытки тестов,
финальный экзамен). Поэтому опыт всегда совпадает с реальным прогрессом и его нельзя «накрутить».
"""
from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Module, ModuleAttempt, ModuleStep, StepProgress

XP_READ = 10        # шаг-материал, видео, ссылка
XP_ACTION = 20      # практическое задание
XP_QUIZ = 50        # пройденный тест модуля
XP_FIRST_TRY = 25   # бонус: тест пройден с первой попытки
XP_FINAL = 100      # отправленный финальный экзамен

# (с какой доли от «базового максимума» XP начинается ранг, название)
RANKS = [
    (0.00, _('Новичок')),
    (0.10, _('Стажёр')),
    (0.30, _('Практик')),
    (0.55, _('Знаток')),
    (0.80, _('Эксперт')),
    (1.00, _('Мастер iBox')),
]


def _step_xp(step):
    return XP_ACTION if step.kind == ModuleStep.Kind.ACTION else XP_READ


def _local_date(moment):
    return timezone.localtime(moment).date()


def _activity_dates(student):
    dates = set()
    for moment in StepProgress.objects.filter(
        student=student, is_done=True, done_at__isnull=False,
    ).values_list('done_at', flat=True):
        dates.add(_local_date(moment))
    for moment in ModuleAttempt.objects.filter(student=student).values_list('created_at', flat=True):
        dates.add(_local_date(moment))
    for moment in student.final_submissions.filter(submitted_at__isnull=False).values_list('submitted_at', flat=True):
        dates.add(_local_date(moment))
    return dates


def streak_days(dates, today=None):
    """Текущая серия: дни подряд с активностью. Серия жива, если сегодня или вчера что-то делали."""
    if not dates:
        return 0
    today = today or timezone.localdate()
    day = today if today in dates else today - timedelta(days=1)
    count = 0
    while day in dates:
        count += 1
        day -= timedelta(days=1)
    return count


def longest_streak(dates):
    best = run = 0
    previous = None
    for day in sorted(dates):
        run = run + 1 if previous is not None and (day - previous).days == 1 else 1
        best = max(best, run)
        previous = day
    return best


def game_state(student, overall_percent=None):
    """XP, ранг, серия и достижения ученика."""
    modules = list(Module.objects.filter(is_published=True))
    module_ids = [module.id for module in modules]
    steps = list(ModuleStep.objects.filter(module_id__in=module_ids))

    done_steps = list(
        StepProgress.objects.filter(student=student, is_done=True, step__module_id__in=module_ids)
        .select_related('step')
    )
    passed_ids = set(student.module_progress.filter(module_id__in=module_ids).values_list('module_id', flat=True))

    first_try_modules = 0
    for module_id in passed_ids:
        first = ModuleAttempt.objects.filter(student=student, module_id=module_id).order_by('created_at', 'id').first()
        if first is not None and first.is_passed:
            first_try_modules += 1

    final_submitted = student.final_submissions.filter(submitted_at__isnull=False).exists()

    xp = (
        sum(_step_xp(record.step) for record in done_steps)
        + len(passed_ids) * XP_QUIZ
        + first_try_modules * XP_FIRST_TRY
        + (XP_FINAL if final_submitted else 0)
    )
    base_max = sum(_step_xp(step) for step in steps) + len(modules) * XP_QUIZ + XP_FINAL

    thresholds = [round(fraction * base_max) for fraction, _name in RANKS]
    index = max(i for i, threshold in enumerate(thresholds) if xp >= threshold)
    is_top = index == len(RANKS) - 1
    if is_top:
        rank_percent, xp_to_next, next_name = 100, 0, None
    else:
        span = max(1, thresholds[index + 1] - thresholds[index])
        rank_percent = round(100 * (xp - thresholds[index]) / span)
        xp_to_next = thresholds[index + 1] - xp
        next_name = RANKS[index + 1][1]

    dates = _activity_dates(student)
    action_done = sum(1 for record in done_steps if record.step.kind == ModuleStep.Kind.ACTION)
    if overall_percent is None:
        from .progress import overall_progress

        overall_percent = overall_progress(student)['percent']

    achievements = [
        {'key': 'first_step', 'icon': 'check', 'title': _('Первый шаг'),
         'hint': _('Отметь первый шаг обучения'), 'earned': bool(done_steps)},
        {'key': 'in_action', 'icon': 'clipboard', 'title': _('В деле'),
         'hint': _('Выполни 3 практических задания'), 'earned': action_done >= 3},
        {'key': 'first_try', 'icon': 'bolt', 'title': _('С первого раза'),
         'hint': _('Пройди тест модуля с первой попытки'), 'earned': first_try_modules > 0},
        {'key': 'rhythm', 'icon': 'flame', 'title': _('В ритме'),
         'hint': _('Занимайся 3 дня подряд'), 'earned': longest_streak(dates) >= 3},
        {'key': 'halfway', 'icon': 'chart', 'title': _('Полпути'),
         'hint': _('Пройди половину онбординга'), 'earned': overall_percent >= 50},
        {'key': 'approved', 'icon': 'star', 'title': _('Допущен к работе'),
         'hint': _('Получи допуск от руководителя'), 'earned': student.status == 'approved'},
    ]

    return {
        'xp': xp,
        'base_max': base_max,
        'rank_index': index,
        'rank_number': index + 1,
        'rank_name': RANKS[index][1],
        'next_rank_name': next_name,
        'rank_percent': rank_percent,
        'xp_to_next': xp_to_next,
        'is_top_rank': is_top,
        'streak': streak_days(dates),
        'achievements': achievements,
        'achievements_earned': sum(1 for item in achievements if item['earned']),
    }
