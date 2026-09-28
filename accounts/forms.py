from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

INPUT_CLASSES = (
    'w-full rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-gray-900 '
    'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 '
    'dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100'
)


class StyledAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES


class RegistrationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = _('Логин')
        self.fields['username'].help_text = _('Например, имя латиницей: aziz.karimov')
        self.fields['password1'].help_text = _('Минимум 8 символов, не только цифры')
        self.fields['password2'].help_text = _('Повтори пароль')
        for field in self.fields.values():
            field.widget.attrs['class'] = INPUT_CLASSES
