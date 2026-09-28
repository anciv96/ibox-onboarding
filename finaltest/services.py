import random

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import Student
from onboarding.models import Module, ModuleProgress

from .models import FinalTestAnswer, FinalTestItem, FinalTestSubmission


def can_start_final_test(student):
    """
    Финальный тест доступен, если все модули пройдены, и это либо первая попытка,
    либо админ явно отправил ученика на доработку (статус needs_rework) — тогда разрешена пересдача.
    """
    total_modules = Module.objects.filter(is_published=True).count()
    if total_modules == 0:
        return False
    completed = ModuleProgress.objects.filter(student=student).count()
    if completed < total_modules:
        return False

    if not student.final_submissions.exists():
        return True
    return student.status == Student.Status.NEEDS_REWORK


MAX_TEXT_LENGTH = 10000


def submission_items(submission):
    """Вопросы конкретной попытки в том порядке, в котором их видит ученик."""
    if not submission.item_ids:  # старые попытки до появления банка вопросов
        return list(FinalTestItem.objects.prefetch_related('options'))
    by_id = {item.id: item for item in FinalTestItem.objects.filter(id__in=submission.item_ids).prefetch_related('options')}
    return [by_id[i] for i in submission.item_ids if i in by_id]


def shuffled_options(submission, item):
    """Порядок вариантов свой у каждой попытки, но стабильный при обновлении страницы."""
    options = list(item.options.all())
    random.Random(f'{submission.pk}-{item.pk}').shuffle(options)
    return options


def clean_final_answers(raw, submission):
    """Допустимые части черновика: id варианта для вопросов с вариантами, текст для открытых и кейсов."""
    if not isinstance(raw, dict):
        return {}
    items = {item.id: item for item in submission_items(submission)}
    cleaned = {}
    for key, value in raw.items():
        try:
            item = items.get(int(key))
        except (TypeError, ValueError):
            continue
        if item is None:
            continue
        if item.type == FinalTestItem.Type.MCQ:
            try:
                option_id = int(value)
            except (TypeError, ValueError):
                continue
            if option_id in {option.id for option in item.options.all()}:
                cleaned[item.id] = option_id
        elif isinstance(value, str) and value.strip():
            cleaned[item.id] = value[:MAX_TEXT_LENGTH]
    return cleaned


def save_final_draft(submission, raw_answers):
    cleaned = clean_final_answers(raw_answers, submission)
    submission.draft = {str(k): v for k, v in cleaned.items()}
    submission.draft_saved_at = timezone.now()
    submission.save(update_fields=['draft', 'draft_saved_at'])
    return cleaned


def get_final_draft(submission):
    return {int(k): v for k, v in (submission.draft or {}).items()}


def pick_item_ids():
    """Случайная выборка из банка: вопросы с вариантами перемешаны, открытые идут в конце."""
    pool = list(FinalTestItem.objects.all())
    closed = [i.id for i in pool if i.type == FinalTestItem.Type.MCQ]
    written = [i.id for i in pool if i.type != FinalTestItem.Type.MCQ]
    closed = random.sample(closed, min(len(closed), settings.FINAL_TEST_MCQ_COUNT))
    written = random.sample(written, min(len(written), settings.FINAL_TEST_OPEN_COUNT))
    return closed + written


@transaction.atomic
def start_submission(student):
    attempt_number = student.final_submissions.count() + 1
    return FinalTestSubmission.objects.create(
        student=student, attempt_number=attempt_number, item_ids=pick_item_ids(),
    )


@transaction.atomic
def submit_answers(submission, answers_payload):
    """
    answers_payload: список {item_id, option_id (для mcq), text_answer (для open/case)}
    Автоматически считается только mcq-часть; открытые вопросы и кейсы ждут ручной/будущей AI-оценки.
    """
    items = {item.id: item for item in submission_items(submission)}
    mcq_total = 0
    mcq_correct = 0

    for payload in answers_payload:
        item = items[payload['item_id']]
        option = None
        is_correct = None
        if item.type == FinalTestItem.Type.MCQ:
            mcq_total += 1
            option = next((o for o in item.options.all() if o.id == payload.get('option_id')), None)
            is_correct = bool(option and option.is_correct)
            if is_correct:
                mcq_correct += 1
        FinalTestAnswer.objects.create(
            submission=submission, item=item, selected_option=option,
            text_answer=payload.get('text_answer', ''), is_correct=is_correct,
        )

    submission.submitted_at = timezone.now()
    submission.mcq_score_percent = round(mcq_correct * 100 / mcq_total) if mcq_total else None
    submission.draft = {}
    submission.draft_saved_at = None
    submission.save(update_fields=['submitted_at', 'mcq_score_percent', 'draft', 'draft_saved_at'])

    student = submission.student
    student.status = Student.Status.PENDING_REVIEW
    student.save(update_fields=['status'])

    return submission
