from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import gettext as _

from core.http import json_draft_endpoint, json_student_endpoint

from .dashboard import build_dashboard
from .gamification import game_state
from .models import Module, ModuleStep
from .services import (
    StepError, clear_module_draft, get_module_draft, is_module_unlocked, save_module_draft,
    set_step_progress, steps_state, submit_module_attempt,
)
from .progress import overall_progress


def _student_or_none(request):
    return getattr(request.user, 'student_profile', None)


@login_required
def dashboard(request):
    student = _student_or_none(request)
    if student is None:
        if request.user.is_staff:
            return redirect('/admin/')
        messages.error(request, _('У этого аккаунта нет профиля ученика.'))
        return redirect('accounts:login')

    return render(request, 'onboarding/dashboard.html', {
        'student': student,
        'd': build_dashboard(student),
    })


def _student_module_or_redirect(request, pk):
    """Общая проверка для страниц модуля: (student, module, redirect_response)."""
    student = _student_or_none(request)
    if student is None:
        if request.user.is_staff:
            return None, None, redirect('/admin/')
        messages.error(request, _('У этого аккаунта нет профиля ученика.'))
        return None, None, redirect('accounts:login')

    module = get_object_or_404(Module, pk=pk, is_published=True)
    if not is_module_unlocked(student, module):
        messages.error(request, _('Сначала пройди предыдущие модули.'))
        return None, None, redirect('onboarding:dashboard')
    return student, module, None


def _module_navigation(module):
    published = list(Module.objects.filter(is_published=True).order_by('order'))
    index = next((i for i, m in enumerate(published) if m.id == module.id), 0)
    return {
        'position': index + 1,
        'total_count': len(published),
        'prev_module': published[index - 1] if index > 0 else None,
        'next_module': published[index + 1] if index + 1 < len(published) else None,
    }


@login_required
def module_detail(request, pk):
    """Страница обучения: шаги (видео, материалы, задания) с отметками «выполнено»."""
    student, module, response = _student_module_or_redirect(request, pk)
    if response:
        return response

    context = {
        'module': module,
        'state': steps_state(student, module),
        'is_completed': student.module_progress.filter(module=module).exists(),
        **_module_navigation(module),
    }
    return render(request, 'onboarding/module_detail.html', context)


@login_required
def module_quiz(request, pk):
    """Проверка знаний по модулю. Открывается, когда выполнены все обязательные шаги обучения."""
    student, module, response = _student_module_or_redirect(request, pk)
    if response:
        return response

    state = steps_state(student, module)
    if not state['quiz_ready']:
        messages.info(request, _('Сначала выполни все обязательные шаги обучения — потом откроется проверка знаний.'))
        return redirect('onboarding:module_detail', pk=module.pk)

    questions = list(module.questions.prefetch_related('options'))

    if request.method == 'POST':
        selected = {}
        for question in questions:
            option_id = request.POST.get(f'question_{question.id}', '')
            if option_id.isdigit():
                selected[question.id] = int(option_id)

        before = game_state(student)
        attempt = submit_module_attempt(student, module, selected)
        if attempt.is_passed:
            clear_module_draft(student, module)
            after = game_state(student)
            gained = after['xp'] - before['xp']
            messages.success(
                request,
                _('Модуль пройден! +%(xp)s XP, значок получен — можно двигаться дальше.') % {'xp': gained},
            )
            if after['rank_index'] > before['rank_index']:
                messages.success(request, _('Новый ранг: %(rank)s!') % {'rank': after['rank_name']})
            return redirect('onboarding:dashboard')

        # Выбор остаётся черновиком, а редирект защищает от повторной отправки формы при обновлении страницы
        save_module_draft(student, module, selected)
        return redirect('onboarding:module_quiz', pk=module.pk)

    draft, draft_saved_at = get_module_draft(student, module)
    last_attempt = module.attempts.filter(student=student).order_by('-created_at', '-id').first()
    failed_attempt = last_attempt if last_attempt and not last_attempt.is_passed else None

    wrong_question_ids = set()
    if failed_attempt:
        for answer in failed_attempt.answers.all():
            # «Неверно» горит, пока ученик не поменял ответ на этот вопрос
            if not answer.is_correct and draft.get(answer.question_id) == answer.selected_option_id:
                wrong_question_ids.add(answer.question_id)
    if not wrong_question_ids:
        failed_attempt = None

    question_rows = [
        {
            'question': question,
            'is_wrong': question.id in wrong_question_ids,
            'options': [
                {'option': option, 'checked': draft.get(question.id) == option.id}
                for option in question.options.all()
            ],
        }
        for question in questions
    ]

    context = {
        'module': module,
        'question_rows': question_rows,
        'is_completed': student.module_progress.filter(module=module).exists(),
        'failed_attempt': failed_attempt,
        'attempts_count': module.attempts.filter(student=student).count(),
        'draft_restored': bool(draft),
        'draft_saved_at': draft_saved_at,
        **_module_navigation(module),
    }
    return render(request, 'onboarding/module_quiz.html', context)


@json_draft_endpoint
def module_draft(request, student, answers, pk):
    module = get_object_or_404(Module, pk=pk, is_published=True)
    if not is_module_unlocked(student, module):
        return JsonResponse({'ok': False, 'error': 'locked'}, status=403)
    cleaned = save_module_draft(student, module, answers)
    return JsonResponse({'ok': True, 'count': len(cleaned), 'saved_at': timezone.localtime().strftime('%H:%M')})


@json_student_endpoint
def module_step(request, student, payload, pk, step_id):
    """Отметка шага выполненным / снятие отметки / автосохранение заметки ученика."""
    module = get_object_or_404(Module, pk=pk, is_published=True)
    if not is_module_unlocked(student, module):
        return JsonResponse({'ok': False, 'error': 'locked'}, status=403)
    step = get_object_or_404(ModuleStep, pk=step_id, module=module)

    done, note = payload.get('done'), payload.get('note')
    if (done is not None and not isinstance(done, bool)) or (note is not None and not isinstance(note, str)):
        return JsonResponse({'ok': False, 'error': 'payload'}, status=400)

    before = game_state(student)
    try:
        record = set_step_progress(student, step, done=done, note=note)
    except StepError as error:
        return JsonResponse({'ok': False, 'error': error.code}, status=422)

    state = steps_state(student, module)
    after = game_state(student)
    return JsonResponse({
        'ok': True,
        'done': record.is_done,
        'done_count': state['done'],
        'total': state['total'],
        'required_done': state['required_done'],
        'required_total': state['required_total'],
        'required_left': state['required_left'],
        'quiz_ready': state['quiz_ready'],
        'overall_percent': overall_progress(student)['percent'],
        'xp': after['xp'],
        'xp_delta': after['xp'] - before['xp'],
        'rank_name': str(after['rank_name']),
        'rank_up': after['rank_index'] > before['rank_index'],
    })
