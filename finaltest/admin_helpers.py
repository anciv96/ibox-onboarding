from django.template.defaultfilters import linebreaksbr
from django.utils.formats import date_format
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.timezone import localtime

from .models import FinalTestItem

CARD_STYLE = 'margin:0 0 12px;padding:10px 14px;border:1px solid rgba(128,128,128,.3);border-radius:8px'
LABEL_STYLE = 'font-size:11px;text-transform:uppercase;letter-spacing:.04em;opacity:.65'


def render_submission_answers(submission):
    """Читаемый вид всех ответов одной попытки финального теста для админки."""
    if submission is None:
        return 'Финальный тест ещё не сдан.'

    header = format_html(
        '<p style="margin:0 0 12px"><b>Попытка №{}</b> · отправлена {} · вопросы с вариантами: {}</p>',
        submission.attempt_number,
        date_format(localtime(submission.submitted_at), 'j E Y, H:i') if submission.submitted_at else 'не отправлена',
        f'{submission.mcq_score_percent}%' if submission.mcq_score_percent is not None else '—',
    )

    cards = []
    answers = submission.answers.select_related('item', 'selected_option').order_by('id')
    for answer in answers:
        if answer.item.type == FinalTestItem.Type.MCQ:
            if answer.selected_option is None:
                body = format_html('<i>ответ не выбран</i>')
            else:
                body = format_html(
                    '{} {}', '✅' if answer.is_correct else '❌', answer.selected_option.text,
                )
                if not answer.is_correct:
                    right = answer.item.options.filter(is_correct=True).first()
                    if right:
                        body = format_html('{}<div style="margin-top:4px;opacity:.75">Правильно: {}</div>', body, right.text)
        else:
            body = linebreaksbr(answer.text_answer) if answer.text_answer else mark_safe('<i>пусто</i>')

        comment = ''
        if answer.admin_comment:
            comment = format_html(
                '<div style="margin-top:8px;padding:6px 10px;border-left:3px solid #2663eb">'
                '<b>Твой комментарий:</b> {}</div>',
                answer.admin_comment,
            )

        cards.append(format_html(
            '<div style="{}"><div style="{}">{}</div>'
            '<div style="font-weight:600;margin:3px 0 8px">{}</div><div>{}</div>{}</div>',
            mark_safe(CARD_STYLE), mark_safe(LABEL_STYLE),
            answer.item.get_type_display(), answer.item.prompt, body, comment,
        ))

    return format_html('{}{}', header, format_html_join('', '{}', ((c,) for c in cards)))
