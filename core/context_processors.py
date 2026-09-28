def onboarding_progress(request):
    """Процент онбординга, ранг и опыт для шапки сайта (только у залогиненного ученика)."""
    user = getattr(request, 'user', None)
    student = getattr(user, 'student_profile', None) if user is not None and user.is_authenticated else None
    if student is None:
        return {}
    from onboarding.gamification import game_state
    from onboarding.progress import overall_progress

    progress = overall_progress(student)
    return {'nav_progress': progress, 'nav_game': game_state(student, overall_percent=progress['percent'])}
