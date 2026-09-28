import functools
import json

from django.http import JsonResponse

MAX_BODY_BYTES = 256 * 1024


def json_student_endpoint(view):
    """
    Обёртка для JSON-эндпоинтов страниц ученика: только POST, только залогиненный ученик, тело — JSON-объект.
    Ошибки отдаются JSON-ом (а не редиректом на логин), чтобы скрипт на странице мог показать понятный статус.
    Во view приходит (request, student, payload, *args).
    """

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.method != 'POST':
            return JsonResponse({'ok': False, 'error': 'method'}, status=405)
        if not request.user.is_authenticated:
            return JsonResponse({'ok': False, 'error': 'auth'}, status=401)
        student = getattr(request.user, 'student_profile', None)
        if student is None:
            return JsonResponse({'ok': False, 'error': 'student'}, status=403)
        if len(request.body) > MAX_BODY_BYTES:
            return JsonResponse({'ok': False, 'error': 'too_large'}, status=413)
        try:
            payload = json.loads(request.body or b'{}')
        except ValueError:
            return JsonResponse({'ok': False, 'error': 'json'}, status=400)
        if not isinstance(payload, dict):
            return JsonResponse({'ok': False, 'error': 'payload'}, status=400)
        return view(request, student, payload, *args, **kwargs)

    return wrapper


def json_draft_endpoint(view):
    """Эндпоинт автосохранения ответов: тело {"answers": {...}}, во view приходит (request, student, answers, *args)."""

    @json_student_endpoint
    @functools.wraps(view)
    def wrapper(request, student, payload, *args, **kwargs):
        answers = payload.get('answers')
        if not isinstance(answers, dict):
            return JsonResponse({'ok': False, 'error': 'answers'}, status=400)
        return view(request, student, answers, *args, **kwargs)

    return wrapper
