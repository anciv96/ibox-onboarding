from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from accounts.models import Student
from finaltest.models import FinalTestItem, FinalTestOption
from finaltest.services import get_final_draft, start_submission, submit_answers
from datetime import date, timedelta

from django.utils import timezone

from onboarding.dashboard import build_dashboard
from onboarding.gamification import XP_ACTION, XP_FINAL, XP_FIRST_TRY, XP_QUIZ, XP_READ, game_state, longest_streak, streak_days
from onboarding.progress import overall_progress
from onboarding.models import (
    Module, ModuleAnswerOption, ModuleProgress, ModuleQuestion, ModuleStep, StepProgress,
)
from onboarding.services import (
    StepError, is_module_unlocked, is_quiz_unlocked, set_step_progress, steps_state, submit_module_attempt,
)

User = get_user_model()


class ModuleAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='student1', password='pass12345')
        self.student = Student.objects.create(user=self.user)
        self.module1 = Module.objects.create(order=1, title='Модуль 1')
        self.module2 = Module.objects.create(order=2, title='Модуль 2')
        self.module3 = Module.objects.create(order=3, title='Модуль 3')

    def test_first_module_is_always_unlocked(self):
        self.assertTrue(is_module_unlocked(self.student, self.module1))

    def test_second_module_locked_until_first_completed(self):
        self.assertFalse(is_module_unlocked(self.student, self.module2))
        ModuleProgress.objects.create(student=self.student, module=self.module1)
        self.assertTrue(is_module_unlocked(self.student, self.module2))

    def test_third_module_locked_even_if_only_first_completed(self):
        ModuleProgress.objects.create(student=self.student, module=self.module1)
        self.assertFalse(is_module_unlocked(self.student, self.module3))


class ModuleAttemptScoringTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='student2', password='pass12345')
        self.student = Student.objects.create(user=self.user)
        self.module = Module.objects.create(order=1, title='Модуль 1')

        self.q1 = ModuleQuestion.objects.create(module=self.module, text='Вопрос 1', order=1)
        self.q1_correct = ModuleAnswerOption.objects.create(question=self.q1, text='Верно', is_correct=True)
        self.q1_wrong = ModuleAnswerOption.objects.create(question=self.q1, text='Неверно', is_correct=False)

        self.q2 = ModuleQuestion.objects.create(module=self.module, text='Вопрос 2', order=2)
        self.q2_correct = ModuleAnswerOption.objects.create(question=self.q2, text='Верно', is_correct=True)
        self.q2_wrong = ModuleAnswerOption.objects.create(question=self.q2, text='Неверно', is_correct=False)

    def test_module_passed_only_if_all_answers_correct(self):
        answers = {self.q1.id: self.q1_correct.id, self.q2.id: self.q2_correct.id}
        attempt = submit_module_attempt(self.student, self.module, answers)

        self.assertTrue(attempt.is_passed)
        self.assertEqual(attempt.correct_count, 2)
        self.assertTrue(
            ModuleProgress.objects.filter(student=self.student, module=self.module).exists()
        )

    def test_module_not_passed_if_one_answer_wrong(self):
        answers = {self.q1.id: self.q1_correct.id, self.q2.id: self.q2_wrong.id}
        attempt = submit_module_attempt(self.student, self.module, answers)

        self.assertFalse(attempt.is_passed)
        self.assertEqual(attempt.correct_count, 1)
        self.assertFalse(
            ModuleProgress.objects.filter(student=self.student, module=self.module).exists()
        )

    def test_failed_attempts_are_logged_and_can_be_retried(self):
        wrong_answers = {self.q1.id: self.q1_wrong.id, self.q2.id: self.q2_wrong.id}
        submit_module_attempt(self.student, self.module, wrong_answers)

        correct_answers = {self.q1.id: self.q1_correct.id, self.q2.id: self.q2_correct.id}
        second_attempt = submit_module_attempt(self.student, self.module, correct_answers)

        self.assertEqual(self.module.attempts.filter(student=self.student).count(), 2)
        self.assertEqual(second_attempt.attempt_number, 2)
        self.assertTrue(second_attempt.is_passed)
        self.assertTrue(
            ModuleProgress.objects.filter(student=self.student, module=self.module).exists()
        )


def make_module(order, title='М', **kwargs):
    module = Module.objects.create(order=order, title=f'{title}{order}', **kwargs)
    question = ModuleQuestion.objects.create(module=module, text='Вопрос', order=1)
    good = ModuleAnswerOption.objects.create(question=question, text='Да', is_correct=True)
    bad = ModuleAnswerOption.objects.create(question=question, text='Нет', is_correct=False)
    return module, question, good, bad


class DashboardBuilderTests(TestCase):
    def setUp(self):
        user = User.objects.create_user('dash', first_name='Дана', password='pass12345')
        self.student = Student.objects.create(user=user)
        self.m1, self.q1, self.q1_good, self.q1_bad = make_module(1)
        self.m2, self.q2, self.q2_good, self.q2_bad = make_module(2)

    def test_rows_reflect_sequential_unlocking(self):
        d = build_dashboard(self.student)
        self.assertEqual([r['state'] for r in d['rows']], ['current', 'locked'])
        self.assertEqual(d['current_module'], self.m1)
        self.assertEqual(d['final_state'], 'locked')
        self.assertFalse(d['can_take_final'])

    def test_rows_match_is_module_unlocked(self):
        submit_module_attempt(self.student, self.m1, {self.q1.id: self.q1_good.id})
        for row in build_dashboard(self.student)['rows']:
            self.assertEqual(row['state'] != 'locked', is_module_unlocked(self.student, row['module']))

    def test_stats_count_attempts_accuracy_and_first_try(self):
        submit_module_attempt(self.student, self.m1, {self.q1.id: self.q1_good.id})   # с первой попытки
        submit_module_attempt(self.student, self.m2, {self.q2.id: self.q2_bad.id})    # провал
        submit_module_attempt(self.student, self.m2, {self.q2.id: self.q2_good.id})   # успех со 2-й

        d = build_dashboard(self.student)
        self.assertEqual(d['modules_done'], 2)
        self.assertEqual(d['percent'], 67)  # 2 теста модулей из 3 зачётных пунктов: финальный экзамен ещё не сдан
        self.assertEqual(d['attempts_total'], 3)
        self.assertEqual(d['failed_total'], 1)
        self.assertEqual(d['first_try_count'], 1)
        self.assertEqual(d['accuracy'], 67)  # 2 верных ответа из 3
        self.assertEqual([r['attempts_count'] for r in d['rows']], [1, 2])
        self.assertTrue(d['all_done'])
        self.assertEqual(d['final_state'], 'ready')
        self.assertTrue(d['can_take_final'])

    def test_accuracy_is_none_without_attempts(self):
        self.assertIsNone(build_dashboard(self.student)['accuracy'])

    def test_events_are_newest_first_and_include_failures(self):
        submit_module_attempt(self.student, self.m1, {self.q1.id: self.q1_bad.id})
        submit_module_attempt(self.student, self.m1, {self.q1.id: self.q1_good.id})
        kinds = [e['kind'] for e in build_dashboard(self.student)['events']]
        self.assertIn('module_failed', kinds)
        self.assertIn('module_passed', kinds)
        self.assertEqual(kinds[-1], 'registered')

    def test_unfinished_final_test_can_be_resumed_from_dashboard(self):
        for module, question, good, _bad in [(self.m1, self.q1, self.q1_good, None), (self.m2, self.q2, self.q2_good, None)]:
            submit_module_attempt(self.student, module, {question.id: good.id})
        start_submission(self.student)  # открыл тест, но не отправил
        d = build_dashboard(self.student)
        self.assertTrue(d['has_open_submission'])
        self.assertTrue(d['can_take_final'])

    def test_decided_statuses_are_shown_even_if_new_module_added_later(self):
        self.student.status = Student.Status.APPROVED
        self.student.save()
        self.assertEqual(build_dashboard(self.student)['final_state'], Student.Status.APPROVED)


class LanguageAndThemeTests(TestCase):
    def setUp(self):
        user = User.objects.create_user('lang', first_name='Анна', password='pass12345')
        self.student = Student.objects.create(user=user)
        self.module, self.question, self.good, self.bad = make_module(1, title_uz='Uzbek nomi')
        ModuleStep.objects.create(
            module=self.module, kind='text', title='Конспект', body='Русский текст', body_uz='Oʻzbekcha matn',
        )
        self.client.force_login(user)

    def switch(self, lang):
        return self.client.post(reverse('set_language'), {'language': lang, 'next': '/'})

    def test_interface_switches_to_uzbek_and_back(self):
        self.assertContains(self.client.get('/'), 'Привет, Анна!')
        self.switch('uz')
        self.assertContains(self.client.get('/'), 'Salom, Анна!')
        self.switch('ru')
        self.assertContains(self.client.get('/'), 'Привет, Анна!')

    def test_language_switcher_is_visible_on_public_pages(self):
        anonymous = self.client_class()
        response = anonymous.get(reverse('accounts:login'))
        self.assertContains(response, reverse('set_language'))
        response = anonymous.post(reverse('set_language'), {'language': 'uz', 'next': reverse('accounts:login')}, follow=True)
        self.assertContains(response, 'Kirish')

    def test_content_uses_uzbek_version_when_filled_and_falls_back_to_russian(self):
        url = reverse('onboarding:module_detail', args=[self.module.pk])
        self.switch('uz')
        response = self.client.get(url)
        self.assertContains(response, 'Uzbek nomi')
        self.assertContains(response, 'Oʻzbekcha matn')
        # вопрос без узбекского текста на странице проверки знаний показывается по-русски
        set_step_progress(self.student, self.module.steps.get(), done=True)  # без выполненного шага тест закрыт
        quiz = self.client.get(reverse('onboarding:module_quiz', args=[self.module.pk]))
        self.assertContains(quiz, 'Вопрос')

    def test_russian_content_shown_by_default(self):
        response = self.client.get(reverse('onboarding:module_detail', args=[self.module.pk]))
        self.assertContains(response, 'Русский текст')
        self.assertNotContains(response, 'Uzbek nomi')

    def test_localized_helper_ignores_empty_uzbek_value(self):
        from core.i18n import localized
        with translation.override('uz'):
            self.assertEqual(localized('ru', ''), 'ru')
            self.assertEqual(localized('ru', 'uz'), 'uz')
        with translation.override('ru'):
            self.assertEqual(localized('ru', 'uz'), 'ru')

    def test_dark_theme_toggle_is_rendered(self):
        response = self.client.get('/')
        self.assertContains(response, 'id="theme-toggle"')
        self.assertContains(response, 'css/app.css')


class ModuleDraftAutosaveTests(TestCase):
    def setUp(self):
        user = User.objects.create_user('saver', password='pass12345')
        self.student = Student.objects.create(user=user)
        self.m1, self.q1, self.q1_good, self.q1_bad = make_module(1)
        self.m2, self.q2, self.q2_good, self.q2_bad = make_module(2)
        self.client.force_login(user)
        self.draft_url = reverse('onboarding:module_draft', args=[self.m1.pk])
        self.page_url = reverse('onboarding:module_quiz', args=[self.m1.pk])

    def save(self, answers, url=None):
        return self.client.post(url or self.draft_url, data={'answers': answers}, content_type='application/json')

    def test_selection_is_saved_and_restored_on_page_load(self):
        response = self.save({str(self.q1.id): self.q1_bad.id})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])

        page = self.client.get(self.page_url)
        self.assertTrue(page.context['draft_restored'])
        checked = [o['option'] for r in page.context['question_rows'] for o in r['options'] if o['checked']]
        self.assertEqual(checked, [self.q1_bad])

    def test_draft_replaces_previous_state_and_can_be_emptied(self):
        self.save({str(self.q1.id): self.q1_bad.id})
        self.save({str(self.q1.id): self.q1_good.id})
        from onboarding.services import get_module_draft
        self.assertEqual(get_module_draft(self.student, self.m1)[0], {self.q1.id: self.q1_good.id})
        self.save({})
        self.assertEqual(get_module_draft(self.student, self.m1)[0], {})

    def test_foreign_and_garbage_ids_are_dropped(self):
        self.save({str(self.q2.id): self.q2_good.id, str(self.q1.id): self.q2_good.id, 'abc': 1, '9999': 1})
        from onboarding.services import get_module_draft
        self.assertEqual(get_module_draft(self.student, self.m1)[0], {})

    def test_passing_the_module_clears_the_draft(self):
        self.save({str(self.q1.id): self.q1_good.id})
        self.client.post(self.page_url, {f'question_{self.q1.id}': self.q1_good.id})
        from onboarding.services import get_module_draft
        self.assertEqual(get_module_draft(self.student, self.m1)[0], {})

    def test_locked_module_cannot_be_saved(self):
        response = self.save({str(self.q2.id): self.q2_good.id}, url=reverse('onboarding:module_draft', args=[self.m2.pk]))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_gets_json_401_not_a_redirect(self):
        anonymous = self.client_class()
        response = anonymous.post(self.draft_url, data={'answers': {}}, content_type='application/json')
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()['ok'])

    def test_bad_requests(self):
        self.assertEqual(self.client.get(self.draft_url).status_code, 405)
        self.assertEqual(self.client.post(self.draft_url, data='not json', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(self.draft_url, data={'answers': [1, 2]}, content_type='application/json').status_code, 400)

    def test_csrf_is_enforced(self):
        from django.test import Client
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.student.user)
        response = strict.post(self.draft_url, data={'answers': {}}, content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_dashboard_mentions_saved_answers(self):
        self.save({str(self.q1.id): self.q1_good.id})
        d = build_dashboard(self.student)
        self.assertTrue(d['rows'][0]['has_draft'])
        self.assertContains(self.client.get('/'), 'Есть сохранённые ответы')


class FinalTestDraftAutosaveTests(TestCase):
    def setUp(self):
        user = User.objects.create_user('finalsaver', password='pass12345')
        self.student = Student.objects.create(user=user)
        module, question, good, _bad = make_module(1)
        submit_module_attempt(self.student, module, {question.id: good.id})
        self.mcq = FinalTestItem.objects.create(type=FinalTestItem.Type.MCQ, prompt='Вопрос', order=1)
        self.opt_ok = FinalTestOption.objects.create(item=self.mcq, text='Да', is_correct=True)
        self.opt_bad = FinalTestOption.objects.create(item=self.mcq, text='Нет')
        self.open_item = FinalTestItem.objects.create(type=FinalTestItem.Type.OPEN, prompt='Расскажи', order=2)
        self.client.force_login(user)
        self.url = reverse('finaltest:draft')
        self.page = reverse('finaltest:take')

    def save(self, answers):
        return self.client.post(self.url, data={'answers': answers}, content_type='application/json')

    def test_cannot_save_before_the_test_was_opened(self):
        self.assertEqual(self.save({}).status_code, 409)

    def test_text_and_choice_survive_reload(self):
        self.client.get(self.page)  # открытие теста создаёт попытку
        response = self.save({str(self.mcq.id): self.opt_bad.id, str(self.open_item.id): 'Мой длинный ответ\nсо второй строкой'})
        self.assertEqual(response.status_code, 200)

        page = self.client.get(self.page)
        self.assertTrue(page.context['draft_restored'])
        self.assertContains(page, 'Мой длинный ответ')
        self.assertTrue(next(o for o in page.context['mcq_rows'][0]['options'] if o['option'] == self.opt_bad)['checked'])

    def test_invalid_parts_are_dropped_and_text_is_capped(self):
        self.client.get(self.page)
        self.save({str(self.mcq.id): 99999, str(self.open_item.id): 'я' * 20000, '777': 'x'})
        submission = self.student.final_submissions.get()
        draft = get_final_draft(submission)
        self.assertNotIn(self.mcq.id, draft)
        self.assertEqual(len(draft[self.open_item.id]), 10000)
        self.assertEqual(set(draft), {self.open_item.id})

    def test_submitting_clears_the_draft(self):
        self.client.get(self.page)
        self.save({str(self.open_item.id): 'черновик'})
        response = self.client.post(self.page, {f'item_{self.mcq.id}': self.opt_ok.id, f'item_{self.open_item.id}': 'итог'})
        self.assertRedirects(response, reverse('finaltest:submitted'))
        submission = self.student.final_submissions.get()
        self.assertEqual(submission.draft, {})
        self.assertEqual(submission.answers.get(item=self.open_item).text_answer, 'итог')

    def test_no_draft_saved_after_submission(self):
        self.client.get(self.page)
        self.client.post(self.page, {f'item_{self.mcq.id}': self.opt_ok.id, f'item_{self.open_item.id}': 'итог'})
        self.assertEqual(self.save({str(self.open_item.id): 'поздно'}).status_code, 409)

    def test_dashboard_offers_to_continue_with_saved_answers(self):
        self.client.get(self.page)
        self.save({str(self.open_item.id): 'черновик'})
        d = build_dashboard(self.student)
        self.assertTrue(d['final_has_draft'])
        self.assertContains(self.client.get('/'), 'Есть сохранённые ответы')

    def test_garbage_choice_in_submit_does_not_crash(self):
        self.client.get(self.page)
        response = self.client.post(self.page, {f'item_{self.mcq.id}': 'abc', f'item_{self.open_item.id}': 'x'})
        self.assertRedirects(response, reverse('finaltest:submitted'))


class LearningStepsTests(TestCase):
    def setUp(self):
        user = User.objects.create_user('learner2', first_name='Лола', password='pass12345')
        self.student = Student.objects.create(user=user)
        self.module, self.question, self.good, self.bad = make_module(1)
        self.video = ModuleStep.objects.create(module=self.module, order=1, kind='video', title='Видео', youtube_id='abc')
        self.text = ModuleStep.objects.create(module=self.module, order=2, kind='text', title='Конспект', body='**Важно**')
        self.task = ModuleStep.objects.create(
            module=self.module, order=3, kind='action', title='Задание', requires_note=True,
        )
        self.optional = ModuleStep.objects.create(
            module=self.module, order=4, kind='resource', title='Ссылка', url='https://example.com', is_required=False,
        )
        self.client.force_login(user)
        self.detail = reverse('onboarding:module_detail', args=[self.module.pk])
        self.quiz = reverse('onboarding:module_quiz', args=[self.module.pk])

    def step_url(self, step):
        return reverse('onboarding:module_step', args=[self.module.pk, step.pk])

    def send(self, step, payload):
        return self.client.post(self.step_url(step), data=payload, content_type='application/json')

    # --- сервис ---
    def test_quiz_locked_until_all_required_steps_done_optional_ignored(self):
        self.assertFalse(is_quiz_unlocked(self.student, self.module))
        set_step_progress(self.student, self.video, done=True)
        set_step_progress(self.student, self.text, done=True)
        self.assertFalse(is_quiz_unlocked(self.student, self.module))  # задание с заметкой ещё не сделано
        set_step_progress(self.student, self.task, done=True, note='Сделал')
        state = steps_state(self.student, self.module)
        self.assertTrue(state['quiz_ready'])
        self.assertEqual((state['required_done'], state['required_total'], state['done'], state['total']), (3, 3, 3, 4))

    def test_module_without_steps_has_open_quiz(self):
        empty, *_ = make_module(2)
        self.assertTrue(is_quiz_unlocked(self.student, empty))

    def test_note_required_step_cannot_be_marked_without_note(self):
        with self.assertRaises(StepError) as raised:
            set_step_progress(self.student, self.task, done=True)
        self.assertEqual(raised.exception.code, 'note_required')
        with self.assertRaises(StepError):
            set_step_progress(self.student, self.task, done=True, note='   ')

    def test_clearing_the_note_unchecks_the_step(self):
        set_step_progress(self.student, self.task, done=True, note='ok')
        record = set_step_progress(self.student, self.task, note='')
        self.assertFalse(record.is_done)
        self.assertIsNone(record.done_at)

    def test_unchecking_keeps_note(self):
        set_step_progress(self.student, self.task, done=True, note='ok')
        record = set_step_progress(self.student, self.task, done=False)
        self.assertFalse(record.is_done)
        self.assertEqual(record.note, 'ok')

    # --- HTTP ---
    def test_learning_page_lists_steps_with_progress(self):
        response = self.client.get(self.detail)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Конспект')
        self.assertContains(response, '<strong>Важно</strong>', html=True)
        self.assertContains(response, 'youtube.com/embed/abc')
        self.assertEqual(response.context['state']['required_left'], 3)

    def test_quiz_redirects_back_to_learning_until_steps_done(self):
        response = self.client.get(self.quiz)
        self.assertRedirects(response, self.detail)
        response = self.client.post(self.quiz, {f'question_{self.question.id}': self.good.id})
        self.assertRedirects(response, self.detail)
        self.assertFalse(self.module.attempts.exists())  # обойти закрытый тест POST-ом нельзя

    def test_quiz_opens_after_required_steps(self):
        for step in (self.video, self.text):
            self.assertEqual(self.send(step, {'done': True}).status_code, 200)
        response = self.send(self.task, {'done': True, 'note': 'Позвонил коллеге'})
        data = response.json()
        self.assertTrue(data['ok'] and data['quiz_ready'] and data['done'])
        self.assertEqual((data['done_count'], data['total'], data['required_left']), (3, 4, 0))
        self.assertEqual(self.client.get(self.quiz).status_code, 200)

    def test_endpoint_requires_note_returns_422_and_does_not_mark(self):
        response = self.send(self.task, {'done': True})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['error'], 'note_required')
        self.assertFalse(StepProgress.objects.filter(student=self.student, is_done=True).exists())

    def test_note_is_autosaved_without_marking_done(self):
        response = self.send(self.task, {'note': 'черновик заметки'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['done'])
        self.assertContains(self.client.get(self.detail), 'черновик заметки')

    def test_can_uncheck_a_step(self):
        self.send(self.video, {'done': True})
        response = self.send(self.video, {'done': False})
        self.assertFalse(response.json()['done'])
        self.assertEqual(response.json()['required_left'], 3)

    def test_step_endpoint_validation_and_access(self):
        self.assertEqual(self.send(self.video, {'done': 'yes'}).status_code, 400)
        self.assertEqual(self.send(self.video, {'note': 123}).status_code, 400)
        other, *_ = make_module(2)
        foreign = ModuleStep.objects.create(module=other, kind='text', title='Чужой')
        response = self.client.post(self.step_url(foreign), data={'done': True}, content_type='application/json')
        self.assertEqual(response.status_code, 404)  # шаг другого модуля
        anonymous = self.client_class()
        self.assertEqual(anonymous.post(self.step_url(self.video), data={}, content_type='application/json').status_code, 401)

    def test_locked_module_steps_cannot_be_changed(self):
        module2, *_ = make_module(2)
        step = ModuleStep.objects.create(module=module2, kind='text', title='Закрытый')
        url = reverse('onboarding:module_step', args=[module2.pk, step.pk])
        self.assertEqual(self.client.post(url, data={'done': True}, content_type='application/json').status_code, 403)

    def test_dashboard_shows_steps_progress(self):
        set_step_progress(self.student, self.video, done=True)
        row = build_dashboard(self.student)['rows'][0]
        self.assertEqual((row['steps_done'], row['steps_total'], row['required_left'], row['quiz_ready']), (1, 4, 2, False))
        self.assertContains(self.client.get('/'), 'Шаги обучения: 1 из 4')

    def test_progress_is_per_student(self):
        set_step_progress(self.student, self.video, done=True)
        other = Student.objects.create(user=User.objects.create_user('other', password='pass12345'))
        self.assertEqual(steps_state(other, self.module)['done'], 0)


class OverallProgressAndAutoOrderTests(TestCase):
    def setUp(self):
        user = User.objects.create_user('prog', first_name='Рано', password='pass12345')
        self.student = Student.objects.create(user=user)
        self.module, self.question, self.good, _bad = make_module(1)
        self.s1 = ModuleStep.objects.create(module=self.module, kind='text', title='Один')
        self.s2 = ModuleStep.objects.create(module=self.module, kind='action', title='Два')
        self.opt = ModuleStep.objects.create(module=self.module, kind='resource', title='Опция', is_required=False)
        self.client.force_login(user)

    # --- общий процент: 2 обязательных шага + тест модуля + финальный экзамен = 4 пункта ---
    def test_overall_progress_counts_required_steps_quiz_and_final(self):
        self.assertEqual(overall_progress(self.student), {'percent': 0, 'done': 0, 'total': 4})
        set_step_progress(self.student, self.s1, done=True)
        self.assertEqual(overall_progress(self.student)['percent'], 25)
        set_step_progress(self.student, self.opt, done=True)  # необязательный шаг не двигает процент
        self.assertEqual(overall_progress(self.student)['percent'], 25)
        set_step_progress(self.student, self.s2, done=True)
        submit_module_attempt(self.student, self.module, {self.question.id: self.good.id})
        self.assertEqual(overall_progress(self.student)['percent'], 75)
        submission = start_submission(self.student)
        submit_answers(submission, [])
        self.assertEqual(overall_progress(self.student)['percent'], 100)

    def test_student_property_and_dashboard_use_the_same_number(self):
        set_step_progress(self.student, self.s1, done=True)
        self.assertEqual(self.student.progress_percent, 25)
        self.assertEqual(build_dashboard(self.student)['percent'], 25)

    def test_header_shows_progress_for_students_only(self):
        set_step_progress(self.student, self.s1, done=True)
        response = self.client.get('/')
        self.assertEqual(response.context['nav_progress']['percent'], 25)
        self.assertContains(response, 'data-nav-progressbar aria-valuenow="25"')
        anonymous = self.client_class().get(reverse('accounts:login'))
        self.assertNotContains(anonymous, 'role="progressbar"')
        staff = User.objects.create_user('staffer', password='pass12345', is_staff=True)
        self.client.force_login(staff)
        self.assertNotIn('nav_progress', self.client.get('/admin/').context)

    def test_step_endpoint_returns_overall_percent_for_live_header(self):
        url = reverse('onboarding:module_step', args=[self.module.pk, self.s1.pk])
        data = self.client.post(url, data={'done': True}, content_type='application/json').json()
        self.assertEqual(data['overall_percent'], 25)

    def test_dashboard_shows_badge_for_passed_module(self):
        page = self.client.get('/')
        self.assertNotContains(page, 'from-amber-300')
        for step in (self.s1, self.s2):
            set_step_progress(self.student, step, done=True)
        submit_module_attempt(self.student, self.module, {self.question.id: self.good.id})
        self.assertContains(self.client.get('/'), 'from-amber-300')

    # --- состояния шагов ---
    def test_step_states_done_current_upcoming(self):
        set_step_progress(self.student, self.s1, done=True)
        states = [row['state'] for row in steps_state(self.student, self.module)['rows']]
        self.assertEqual(states, ['done', 'current', 'upcoming'])
        set_step_progress(self.student, self.s1, done=False)
        states = [row['state'] for row in steps_state(self.student, self.module)['rows']]
        self.assertEqual(states, ['current', 'upcoming', 'upcoming'])

    def test_learning_page_opens_only_current_step(self):
        page = self.client.get(reverse('onboarding:module_detail', args=[self.module.pk]))
        self.assertContains(page, 'data-state="current" data-open="1"', count=1)
        self.assertContains(page, 'data-state="upcoming" data-open="0"', count=2)

    # --- автоматический порядок ---
    def test_new_records_get_next_order_automatically(self):
        self.assertEqual([s.order for s in self.module.steps.all()], [1, 2, 3])
        q2 = ModuleQuestion.objects.create(module=self.module, text='Второй')
        self.assertEqual((self.question.order, q2.order), (1, 2))
        m2 = Module.objects.create(title='Второй модуль')
        self.assertEqual(m2.order, 2)
        item1 = FinalTestItem.objects.create(type='open', prompt='а')
        item2 = FinalTestItem.objects.create(type='open', prompt='б')
        self.assertEqual((item1.order, item2.order), (1, 2))

    def test_explicit_order_is_respected_and_next_follows_the_highest(self):
        step = ModuleStep.objects.create(module=self.module, kind='text', title='Явный', order=10)
        self.assertEqual(step.order, 10)
        self.assertEqual(ModuleStep.objects.create(module=self.module, kind='text', title='После').order, 11)

    def test_order_is_independent_between_modules(self):
        other, *_ = make_module(2)
        self.assertEqual(ModuleStep.objects.create(module=other, kind='text', title='первый в другом').order, 1)


class GamificationTests(TestCase):
    def setUp(self):
        user = User.objects.create_user('gamer', first_name='Игрок', password='pass12345')
        self.student = Student.objects.create(user=user)
        self.module, self.question, self.good, self.bad = make_module(1)
        self.read = ModuleStep.objects.create(module=self.module, kind='text', title='Читать')
        self.task = ModuleStep.objects.create(module=self.module, kind='action', title='Делать')
        self.client.force_login(user)
        # максимум XP без бонусов: 10 + 20 + 50 + 100 = 180; пороги рангов: 0 / 18 / 54 / 99 / 144 / 180

    def rank(self):
        return str(game_state(self.student)['rank_name'])

    def test_xp_grows_with_steps_quiz_and_final(self):
        self.assertEqual((game_state(self.student)['xp'], self.rank()), (0, 'Новичок'))
        set_step_progress(self.student, self.read, done=True)
        self.assertEqual(game_state(self.student)['xp'], XP_READ)
        set_step_progress(self.student, self.task, done=True)
        self.assertEqual((game_state(self.student)['xp'], self.rank()), (XP_READ + XP_ACTION, 'Стажёр'))
        submit_module_attempt(self.student, self.module, {self.question.id: self.good.id})
        expected = XP_READ + XP_ACTION + XP_QUIZ + XP_FIRST_TRY
        self.assertEqual((game_state(self.student)['xp'], self.rank()), (expected, 'Знаток'))
        submit_answers(start_submission(self.student), [])
        state = game_state(self.student)
        self.assertEqual(state['xp'], expected + XP_FINAL)
        self.assertEqual((str(state['rank_name']), state['is_top_rank']), ('Мастер iBox', True))

    def test_first_try_bonus_only_when_first_attempt_passed(self):
        set_step_progress(self.student, self.read, done=True)
        set_step_progress(self.student, self.task, done=True)
        submit_module_attempt(self.student, self.module, {self.question.id: self.bad.id})
        submit_module_attempt(self.student, self.module, {self.question.id: self.good.id})
        self.assertEqual(game_state(self.student)['xp'], XP_READ + XP_ACTION + XP_QUIZ)

    def test_unchecking_removes_xp_so_it_cannot_be_farmed(self):
        set_step_progress(self.student, self.read, done=True)
        set_step_progress(self.student, self.read, done=False)
        self.assertEqual(game_state(self.student)['xp'], 0)

    def test_rank_progress_towards_next_rank(self):
        set_step_progress(self.student, self.read, done=True)  # 10 XP из 18 до «Стажёра»
        state = game_state(self.student)
        self.assertEqual((state['xp_to_next'], state['rank_percent']), (8, 56))
        self.assertEqual(str(state['next_rank_name']), 'Стажёр')

    def test_streak_counts_consecutive_days(self):
        today = date(2026, 9, 26)
        self.assertEqual(streak_days({today - timedelta(days=2), today - timedelta(days=1), today}, today), 3)
        self.assertEqual(streak_days({today - timedelta(days=1)}, today), 1)      # сегодня ещё не занимался, серия жива
        self.assertEqual(streak_days({today - timedelta(days=2)}, today), 0)      # пропущен целый день
        self.assertEqual(streak_days({today - timedelta(days=3), today}, today), 1)
        self.assertEqual(streak_days(set(), today), 0)
        self.assertEqual(longest_streak({date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 10)}), 3)

    def test_streak_from_real_activity_and_achievement(self):
        now = timezone.now()
        for offset, step in enumerate((self.read, self.task)):
            set_step_progress(self.student, step, done=True)
        from onboarding.models import StepProgress
        StepProgress.objects.filter(step=self.read).update(done_at=now - timedelta(days=2))
        StepProgress.objects.filter(step=self.task).update(done_at=now - timedelta(days=1))
        submit_module_attempt(self.student, self.module, {self.question.id: self.good.id})  # сегодня
        state = game_state(self.student)
        self.assertEqual(state['streak'], 3)
        self.assertTrue(next(a for a in state['achievements'] if a['key'] == 'rhythm')['earned'])

    def test_achievements(self):
        earned = lambda: {a['key'] for a in game_state(self.student)['achievements'] if a['earned']}
        self.assertEqual(earned(), set())
        set_step_progress(self.student, self.read, done=True)
        self.assertEqual(earned(), {'first_step'})
        set_step_progress(self.student, self.task, done=True)
        submit_module_attempt(self.student, self.module, {self.question.id: self.good.id})
        self.assertEqual(earned(), {'first_step', 'first_try', 'halfway'})

    def test_levels_scale_with_content_amount(self):
        base = game_state(self.student)['base_max']
        ModuleStep.objects.create(module=self.module, kind='action', title='Ещё задание')
        self.assertEqual(game_state(self.student)['base_max'], base + XP_ACTION)

    def test_step_endpoint_reports_xp_and_header_updates_live(self):
        url = reverse('onboarding:module_step', args=[self.module.pk, self.task.pk])
        data = self.client.post(url, data={'done': True, 'note': ''}, content_type='application/json').json()
        self.assertEqual((data['xp'], data['xp_delta'], data['rank_up']), (XP_ACTION, XP_ACTION, True))  # 20 XP: с «Новичка» на «Стажёра»
        self.assertEqual(data['rank_name'], 'Стажёр')
        again = self.client.post(url, data={'done': True}, content_type='application/json').json()
        self.assertEqual((again['xp_delta'], again['rank_up']), (0, False))

    def test_quiz_pass_message_mentions_xp_and_rank(self):
        for step in (self.read, self.task):
            set_step_progress(self.student, step, done=True)
        response = self.client.post(
            reverse('onboarding:module_quiz', args=[self.module.pk]),
            {f'question_{self.question.id}': self.good.id}, follow=True,
        )
        text = ' '.join(str(m) for m in response.context['messages'])
        self.assertIn(f'+{XP_QUIZ + XP_FIRST_TRY} XP', text)
        self.assertIn('Новый ранг', text)

    def test_dashboard_and_header_show_rank_xp_and_achievements(self):
        set_step_progress(self.student, self.read, done=True)
        page = self.client.get('/')
        self.assertContains(page, 'data-nav-xp')
        self.assertContains(page, 'Достижения')
        self.assertContains(page, 'Первый шаг')
        self.assertEqual(page.context['d']['game']['xp'], XP_READ)


class NoteRequirementOnlyForActionsTests(TestCase):
    def test_requires_note_flag_on_a_reading_step_does_not_block_marking_it_done(self):
        user = User.objects.create_user('reader', password='pass12345')
        student = Student.objects.create(user=user)
        module, *_ = make_module(1)
        reading = ModuleStep.objects.create(module=module, kind='text', title='Материал', requires_note=True)
        record = set_step_progress(student, reading, done=True)
        self.assertTrue(record.is_done)
        self.assertFalse(reading.needs_note)
        task = ModuleStep.objects.create(module=module, kind='action', title='Задание', requires_note=True)
        self.assertTrue(task.needs_note)
        with self.assertRaises(StepError):
            set_step_progress(student, task, done=True)
