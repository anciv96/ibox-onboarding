from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from .forms import RegistrationForm
from .models import Invitation, Student


def register(request, token):
    invitation = get_object_or_404(Invitation, token=token)

    if invitation.status == Invitation.Status.USED:
        messages.info(request, _('Эта ссылка уже использована. Войди под своим логином и паролем.'))
        return redirect('accounts:login')
    if invitation.status == Invitation.Status.REVOKED:
        messages.error(request, _('Эта ссылка больше недействительна. Обратись к руководителю.'))
        return redirect('accounts:login')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            first_name, _sep, last_name = invitation.full_name.partition(' ')
            user = form.save(commit=False)
            user.first_name = first_name
            user.last_name = last_name
            user.save()

            Student.objects.create(user=user, invitation=invitation)
            invitation.status = Invitation.Status.USED
            invitation.used_at = timezone.now()
            invitation.save(update_fields=['status', 'used_at'])

            auth_login(request, user)
            return redirect('onboarding:dashboard')
    else:
        form = RegistrationForm()

    return render(request, 'accounts/register.html', {'invitation': invitation, 'form': form})
