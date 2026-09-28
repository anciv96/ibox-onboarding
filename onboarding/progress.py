from .models import Module, ModuleStep, StepProgress


def overall_progress(student):
    """
    Процент прохождения ВСЕГО онбординга: обязательные шаги всех модулей + тест каждого модуля
    + финальный экзамен (засчитывается, когда отправлен). Одно число для шапки, дашборда и админки.
    """
    modules = list(Module.objects.filter(is_published=True))
    if not modules:
        return {'percent': 0, 'done': 0, 'total': 0}

    passed_ids = set(student.module_progress.values_list('module_id', flat=True))
    done_step_ids = set(
        StepProgress.objects.filter(student=student, is_done=True).values_list('step_id', flat=True)
    )
    required_step_ids = list(
        ModuleStep.objects.filter(module__in=modules, is_required=True).values_list('id', flat=True)
    )
    final_submitted = student.final_submissions.filter(submitted_at__isnull=False).exists()

    done = (
        sum(1 for module in modules if module.id in passed_ids)
        + sum(1 for step_id in required_step_ids if step_id in done_step_ids)
        + (1 if final_submitted else 0)
    )
    total = len(modules) + len(required_step_ids) + 1
    return {'percent': round(done * 100 / total), 'done': done, 'total': total}
