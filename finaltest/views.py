from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from core.http import json_draft_endpoint

from .models import FinalTestItem
from .services import (
    can_start_final_test, get_final_draft, save_final_draft, shuffled_options, start_submission,
    submission_items, submit_answers,
)


def _student_or_none(request):
    return getattr(request.user, 'student_profile', None)


def _open_submission(student):
    return student.final_submissions.filter(submitted_at__isnull=True).order_by('-started_at').first()


@login_required
def take_test(request):
    student = _student_or_none(request)
    if student is None:
        if request.user.is_staff:
            return redirect('/admin/')
        messages.error(request, _('У этого аккаунта нет профиля ученика.'))
        return redirect('accounts:login')

    submission = _open_submission(student)
    if submission is None:
        if not can_start_final_test(student):
            messages.error(request, _('Финальный тест пока недоступен.'))
            return redirect('onboarding:dashboard')
        submission = start_submission(student)

    items = submission_items(submission)

    if request.method == 'POST':
        answers_payload = []
        for item in items:
            if item.type == FinalTestItem.Type.MCQ:
                option_id = request.POST.get(f'item_{item.id}')
                answers_payload.append({
                    'item_id': item.id,
                    'option_id': int(option_id) if option_id and option_id.isdigit() else None,
                })
            else:
                answers_payload.append({
                    'item_id': item.id,
                    'text_answer': request.POST.get(f'item_{item.id}', '').strip(),
                })
        submit_answers(submission, answers_payload)
        return redirect('finaltest:submitted')

    draft = get_final_draft(submission)
    context = {
        'mcq_rows': [
            {
                'item': item,
                'options': [
                    {'option': option, 'checked': draft.get(item.id) == option.id}
                    for option in shuffled_options(submission, item)
                ],
            }
            for item in items if item.type == FinalTestItem.Type.MCQ
        ],
        'open_rows': [
            {'item': item, 'text': draft.get(item.id, '')}
            for item in items if item.type != FinalTestItem.Type.MCQ
        ],
        'attempt_number': submission.attempt_number,
        'total_items': len(items),
        'draft_restored': bool(draft),
        'draft_saved_at': submission.draft_saved_at,
    }
    return render(request, 'finaltest/take_test.html', context)


@json_draft_endpoint
def save_draft(request, student, answers):
    submission = _open_submission(student)
    if submission is None:
        return JsonResponse({'ok': False, 'error': 'no_open_attempt'}, status=409)
    cleaned = save_final_draft(submission, answers)
    return JsonResponse({'ok': True, 'count': len(cleaned), 'saved_at': timezone.localtime().strftime('%H:%M')})


@login_required
def submitted(request):
    student = _student_or_none(request)
    if student is None:
        return redirect('accounts:login')
    return render(request, 'finaltest/submitted.html')
