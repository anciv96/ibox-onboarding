from django.utils.translation import get_language


def is_uzbek():
    return (get_language() or '').startswith('uz')


def localized(ru_value, uz_value):
    """Узбекская версия контента, если выбран узбекский и она заполнена, иначе русская."""
    return uz_value if is_uzbek() and uz_value else ru_value
