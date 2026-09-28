from django.db import transaction
from django.utils import timezone

from .models import (
    Module, ModuleAttempt, ModuleAttemptAnswer, ModuleDraft, ModuleProgress, StepProgress,
)


def is_module_unlocked(student, module):
    """Модуль доступен, если это первый модуль, либо предыдущий уже пройден."""
    previous = (
        Module.objects.filter(is_published=True, order__lt=module.order)
        .order_by('-order')
        .first()
    )
    if previous is None:
        return True
    return ModuleProgress.objects.filter(student=student, module=previous).exists()


@transaction.atomic
def submit_module_attempt(student, module, selected_option_ids_by_question):
    """
    Проверяет ответы ученика на контрольные вопросы модуля.
    Модуль засчитывается, только если ВСЕ вопросы отвечены верно.
    Каждая попытка (в том числе неудачная) логируется.

    selected_option_ids_by_question: {question_id: option_id}
    """
    questions = list(module.questions.prefetch_related('options'))
    attempt_number = ModuleAttempt.objects.filter(student=student, module=module).count() + 1
    attempt = ModuleAttempt.objects.create(
        student=student, module=module, attempt_number=attempt_number,
        total_count=len(questions),
    )

    correct_count = 0
    for question in questions:
        option_id = selected_option_ids_by_question.get(question.id)
        option = next((o for o in question.options.all() if o.id == option_id), None)
        is_correct = bool(option and option.is_correct)
        if is_correct:
            correct_count += 1
        if option is not None:
            ModuleAttemptAnswer.objects.create(
                attempt=attempt, question=question, selected_option=option, is_correct=is_correct,
            )

    attempt.correct_count = correct_count
    attempt.is_passed = bool(questions) and correct_count == len(questions)
    attempt.save(update_fields=['correct_count', 'is_passed'])

    if attempt.is_passed:
        ModuleProgress.objects.get_or_create(student=student, module=module)

    return attempt


def clean_module_answers(module, raw):
    """Оставляет только пары «вопрос этого модуля → вариант этого вопроса»; всё остальное отбрасывает."""
    if not isinstance(raw, dict):
        return {}
    valid = {
        question.id: {option.id for option in question.options.all()}
        for question in module.questions.prefetch_related('options')
    }
    cleaned = {}
    for key, value in raw.items():
        try:
            question_id, option_id = int(key), int(value)
        except (TypeError, ValueError):
            continue
        if option_id in valid.get(question_id, ()):
            cleaned[question_id] = option_id
    return cleaned


def save_module_draft(student, module, raw_answers):
    cleaned = clean_module_answers(module, raw_answers)
    if cleaned:
        ModuleDraft.objects.update_or_create(
            student=student, module=module,
            defaults={'answers': {str(k): v for k, v in cleaned.items()}},
        )
    else:
        ModuleDraft.objects.filter(student=student, module=module).delete()
    return cleaned


def get_module_draft(student, module):
    draft = ModuleDraft.objects.filter(student=student, module=module).first()
    if draft is None:
        return {}, None
    return {int(k): v for k, v in draft.answers.items()}, draft.updated_at


def clear_module_draft(student, module):
    ModuleDraft.objects.filter(student=student, module=module).delete()


MAX_NOTE_LENGTH = 2000


class StepError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def steps_state(student, module):
    """Шаги обучения модуля с отметками ученика и готовностью к тесту (все обязательные шаги выполнены)."""
    progress = {p.step_id: p for p in StepProgress.objects.filter(student=student, step__module=module)}
    rows = []
    for step in module.steps.all():
        record = progress.get(step.id)
        rows.append({
            'step': step,
            'done': bool(record and record.is_done),
            'note': record.note if record else '',
        })
    # Движение по пути: выполненные — done, первый невыполненный — current, остальные — upcoming
    current_found = False
    for row in rows:
        if row['done']:
            row['state'] = 'done'
        elif not current_found:
            row['state'] = 'current'
            current_found = True
        else:
            row['state'] = 'upcoming'

    required = [row for row in rows if row['step'].is_required]
    required_done = sum(1 for row in required if row['done'])
    return {
        'rows': rows,
        'total': len(rows),
        'done': sum(1 for row in rows if row['done']),
        'required_total': len(required),
        'required_done': required_done,
        'required_left': len(required) - required_done,
        'quiz_ready': required_done == len(required),
    }


def is_quiz_unlocked(student, module):
    """Тест модуля открывается, когда выполнены все обязательные шаги обучения (нет шагов — открыт сразу)."""
    return steps_state(student, module)['quiz_ready']


def set_step_progress(student, step, done=None, note=None):
    """
    Меняет отметку и/или заметку ученика по шагу. Практическое задание с «нужна заметка» нельзя
    отметить без заметки; если заметку стёрли — отметка снимается.
    """
    record, _created = StepProgress.objects.get_or_create(student=student, step=step)
    if note is not None:
        record.note = note[:MAX_NOTE_LENGTH]
    if done is not None:
        if done and step.needs_note and not record.note.strip():
            raise StepError('note_required')
        record.is_done = done
        record.done_at = timezone.now() if done else None
    if step.needs_note and record.is_done and not record.note.strip():
        record.is_done = False
        record.done_at = None
    record.save()
    return record
