from django.db.models import Max


def next_order(queryset):
    """Следующий порядковый номер: за последним элементом выборки."""
    return (queryset.aggregate(top=Max('order'))['top'] or 0) + 1
