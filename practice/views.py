from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .models import PracticeQuestion
from .services import new_round, record_answer, shuffled_options, stats

SESSION_KEY = 'practice_round'


def _student(request):
    return getattr(request.user, 'student_profile', None)


def _guard(request):
    student = _student(request)
    if student is None:
        if request.user.is_staff:
            return None, redirect('/admin/')
        messages.error(request, _('У этого аккаунта нет профиля ученика.'))
        return None, redirect('accounts:login')
    return student, None


@login_required
def lobby(request):
    student, response = _guard(request)
    if response:
        return response
    return render(request, 'practice/lobby.html', {'stats': stats(student), 'has_round': bool(request.session.get(SESSION_KEY))})


@login_required
@require_POST
def start(request):
    student, response = _guard(request)
    if response:
        return response
    category = request.POST.get('category', '')
    if category not in PracticeQuestion.Category.values:
        category = ''
    round_state = new_round(student, category or None)
    if round_state is None:
        messages.info(request, _('В этой игре пока нет вопросов.'))
        return redirect('practice:lobby')
    request.session[SESSION_KEY] = round_state
    return redirect('practice:play')


def _current_question(round_state):
    """Текущий вопрос раунда; удалённые из базы вопросы пропускаются."""
    while round_state['i'] < len(round_state['ids']):
        question = PracticeQuestion.objects.filter(pk=round_state['ids'][round_state['i']], is_published=True).prefetch_related('options').first()
        if question is not None:
            return question
        round_state['i'] += 1
    return None


@login_required
def play(request):
    student, response = _guard(request)
    if response:
        return response
    round_state = request.session.get(SESSION_KEY)
    if not round_state:
        return redirect('practice:lobby')
    total = len(round_state['ids'])

    if request.method == 'POST':
        pending = round_state.get('pending')
        if request.POST.get('action') == 'next' and pending:
            round_state['i'] += 1
            round_state['pending'] = None
        elif request.POST.get('action') == 'answer' and not pending:
            question = _current_question(round_state)
            option_id = request.POST.get('option', '')
            if question is not None and option_id.isdigit():
                result = record_answer(student, question, int(option_id))
                if result is not None:
                    option, is_correct = result
                    round_state['pending'] = [question.id, option.id, is_correct]
                    round_state['results'].append([question.id, option.id, is_correct])
        request.session[SESSION_KEY] = round_state
        return redirect('practice:play')

    question = _current_question(round_state)
    request.session[SESSION_KEY] = round_state
    correct_count = sum(1 for _q, _o, ok in round_state['results'] if ok)

    if question is None:  # раунд закончен
        missed = []
        for question_id, option_id, ok in round_state['results']:
            if ok:
                continue
            item = PracticeQuestion.objects.filter(pk=question_id).prefetch_related('options').first()
            if item is not None:
                missed.append({
                    'question': item,
                    'chosen': next((o for o in item.options.all() if o.id == option_id), None),
                    'right': next((o for o in item.options.all() if o.is_correct), None),
                })
        answered = len(round_state['results'])
        return render(request, 'practice/summary.html', {
            'correct': correct_count, 'answered': answered, 'missed': missed,
            'percent': round(100 * correct_count / answered) if answered else 0,
            'category': round_state.get('category', ''),
        })

    pending = round_state.get('pending')
    options = shuffled_options(round_state['token'], question)
    context = {
        'question': question, 'position': round_state['i'] + 1, 'total': total,
        'correct_count': correct_count, 'category_label': question.get_category_display(),
        'is_myth': question.category == PracticeQuestion.Category.MYTH,
    }
    if pending and pending[0] == question.id:
        context['feedback'] = {'chosen_id': pending[1], 'is_correct': pending[2]}
        context['is_last'] = round_state['i'] + 1 >= total
    context['options'] = options
    return render(request, 'practice/play.html', context)
