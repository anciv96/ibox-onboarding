from collections import defaultdict

from django.utils import timezone

from accounts.models import Student
from finaltest.services import can_start_final_test

from .gamification import game_state
from .models import Module, ModuleStep, StepProgress
from .progress import overall_progress

EVENTS_LIMIT = 8
RING_LENGTH = 327  # длина окружности кольца прогресса в SVG (r=52)


def build_dashboard(student):
    """Все данные для личного дашборда ученика: путь по модулям, статистика, финальный тест, лента."""
    modules = list(Module.objects.filter(is_published=True).order_by('order'))
    progress = {p.module_id: p for p in student.module_progress.all()}
    attempts = list(student.module_attempts.select_related('module').order_by('created_at', 'id'))
    steps_by_module = defaultdict(list)
    for step in ModuleStep.objects.filter(module__in=modules):
        steps_by_module[step.module_id].append(step)
    done_step_ids = set(
        StepProgress.objects.filter(student=student, is_done=True).values_list('step_id', flat=True)
    )
    drafted_module_ids = {d.module_id for d in student.module_drafts.all() if d.answers}
    attempts_by_module = defaultdict(list)
    for attempt in attempts:
        attempts_by_module[attempt.module_id].append(attempt)

    rows = []
    current_module = None
    previous_done = True
    for module in modules:
        done = module.id in progress
        module_attempts = attempts_by_module.get(module.id, [])
        module_steps = steps_by_module.get(module.id, [])
        required_left = sum(1 for st in module_steps if st.is_required and st.id not in done_step_ids)
        if done:
            state = 'done'
        elif previous_done:
            state = 'current'
            current_module = current_module or module
        else:
            state = 'locked'
        rows.append({
            'module': module,
            'state': state,
            'completed_at': progress[module.id].completed_at if done else None,
            'attempts_count': len(module_attempts),
            'failed_count': sum(1 for a in module_attempts if not a.is_passed),
            'steps_total': len(module_steps),
            'steps_done': sum(1 for st in module_steps if st.id in done_step_ids),
            'required_left': required_left,
            'quiz_ready': required_left == 0,
            'has_draft': (not done) and module.id in drafted_module_ids,
            'first_try': bool(done and module_attempts and module_attempts[0].is_passed),
            'last_attempt': module_attempts[-1] if module_attempts else None,
        })
        previous_done = done

    modules_total = len(modules)
    modules_done = sum(1 for row in rows if row['state'] == 'done')
    all_done = modules_total > 0 and modules_done == modules_total

    answers_total = sum(a.total_count for a in attempts)
    answers_correct = sum(a.correct_count for a in attempts)

    started_on = timezone.localtime(student.started_at).date()
    days_in_course = max(1, (timezone.localdate() - started_on).days + 1)

    submissions = list(
        student.final_submissions.filter(submitted_at__isnull=False).order_by('submitted_at')
    )
    open_submission = student.final_submissions.filter(submitted_at__isnull=True).first()
    has_open_submission = open_submission is not None

    if student.status in (Student.Status.APPROVED, Student.Status.REJECTED, Student.Status.PENDING_REVIEW):
        final_state = student.status
    elif not all_done:
        final_state = 'locked'
    elif student.status == Student.Status.NEEDS_REWORK:
        final_state = Student.Status.NEEDS_REWORK
    else:
        final_state = 'ready'

    can_take_final = all_done and (has_open_submission or can_start_final_test(student))

    events = [{'kind': 'registered', 'when': student.started_at}]
    for module_id, item in progress.items():
        events.append({
            'kind': 'module_passed', 'when': item.completed_at,
            'module': next((m for m in modules if m.id == module_id), item.module),
        })
    for attempt in attempts:
        if not attempt.is_passed:
            events.append({
                'kind': 'module_failed', 'when': attempt.created_at, 'module': attempt.module,
                'correct': attempt.correct_count, 'total': attempt.total_count,
            })
    for submission in submissions:
        events.append({
            'kind': 'final_submitted', 'when': submission.submitted_at,
            'attempt': submission.attempt_number,
        })
    events.sort(key=lambda e: e['when'], reverse=True)

    percent = overall_progress(student)['percent']

    return {
        'rows': rows,
        'current_module': current_module,
        'modules_total': modules_total,
        'modules_done': modules_done,
        'percent': percent,
        'game': game_state(student, overall_percent=percent),
        'ring': round(percent * RING_LENGTH / 100),
        'all_done': all_done,
        'attempts_total': len(attempts),
        'failed_total': sum(1 for a in attempts if not a.is_passed),
        'first_try_count': sum(1 for row in rows if row['first_try']),
        'accuracy': round(answers_correct * 100 / answers_total) if answers_total else None,
        'days_in_course': days_in_course,
        'started_at': student.started_at,
        'final_state': final_state,
        'can_take_final': can_take_final,
        'has_open_submission': has_open_submission,
        'final_has_draft': bool(open_submission and open_submission.draft),
        'submissions': submissions,
        'events': events[:EVENTS_LIMIT],
    }
