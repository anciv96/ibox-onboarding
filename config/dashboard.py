from django.contrib.staticfiles import finders
from django.db.models import Count, Max, Q
from django.templatetags.static import static
from django.urls import reverse

from accounts.models import Invitation, Student


def site_icon(request):
    """Логотип в шапке админки: подхватится сам, как только появится static/logo.png."""
    return static('logo.png') if finders.find('logo.png') else None


def pending_review_badge(request):
    """Красный счётчик у пункта «Ученики» — сколько работ ждут решения."""
    return Student.objects.filter(status=Student.Status.PENDING_REVIEW).count() or None


def dashboard_callback(request, context):
    student_list = reverse('admin:accounts_student_changelist')
    counts = {
        row['status']: row['n']
        for row in Student.objects.values('status').annotate(n=Count('id'))
    }
    pending_invites = Invitation.objects.filter(status=Invitation.Status.PENDING).count()

    context['stats'] = [
        {
            'label': 'Ждут вашего решения',
            'value': counts.get(Student.Status.PENDING_REVIEW, 0),
            'href': f'{student_list}?status__exact={Student.Status.PENDING_REVIEW}',
            'icon': 'fact_check',
            'highlight': counts.get(Student.Status.PENDING_REVIEW, 0) > 0,
        },
        {
            'label': 'Проходят обучение',
            'value': counts.get(Student.Status.IN_PROGRESS, 0),
            'href': f'{student_list}?status__exact={Student.Status.IN_PROGRESS}',
            'icon': 'school',
        },
        {
            'label': 'Допущено к работе',
            'value': counts.get(Student.Status.APPROVED, 0),
            'href': f'{student_list}?status__exact={Student.Status.APPROVED}',
            'icon': 'verified',
        },
        {
            'label': 'Приглашения без регистрации',
            'value': pending_invites,
            'href': f"{reverse('admin:accounts_invitation_changelist')}?status__exact={Invitation.Status.PENDING}",
            'icon': 'mail',
        },
    ]

    pending = (
        Student.objects.filter(status=Student.Status.PENDING_REVIEW)
        .select_related('user')
        .annotate(
            last_submitted=Max('final_submissions__submitted_at'),
            submissions=Count('final_submissions', filter=Q(final_submissions__submitted_at__isnull=False)),
        )
        .order_by('last_submitted')
    )
    context['pending_rows'] = [
        {
            'name': str(student),
            'url': reverse('admin:accounts_student_change', args=[student.pk]),
            'submitted_at': student.last_submitted,
            'attempt': student.submissions,
        }
        for student in pending
    ]

    learning = Student.objects.filter(status=Student.Status.IN_PROGRESS).select_related('user')[:8]
    context['learning_rows'] = [
        {
            'name': str(student),
            'url': reverse('admin:accounts_student_change', args=[student.pk]),
            'module': student.current_module,
            'percent': student.progress_percent,
        }
        for student in learning
    ]

    context['new_invite_url'] = reverse('admin:accounts_invitation_add')
    return context
