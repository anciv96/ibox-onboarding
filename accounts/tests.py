from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Invitation, Student
from finaltest.models import FinalTestItem, FinalTestOption
from finaltest.services import start_submission, submit_answers
from onboarding.models import Module, ModuleAnswerOption, ModuleQuestion, ModuleStep
from onboarding.services import set_step_progress

User = get_user_model()


class AdminPagesSmokeTests(TestCase):
    """Все страницы админки открываются без ошибок и содержат нужные данные."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('boss', 'boss@example.com', 'pass12345')
        cls.invitation = Invitation.objects.create(full_name='Тест Стажёров')

        user = User.objects.create_user('intern', first_name='Иван', last_name='Иванов', password='pass12345')
        cls.student = Student.objects.create(user=user)
        item = FinalTestItem.objects.create(type=FinalTestItem.Type.OPEN, prompt='Расскажи о себе', order=1)
        mcq = FinalTestItem.objects.create(type=FinalTestItem.Type.MCQ, prompt='Выбери верное', order=2)
        cls.option = FinalTestOption.objects.create(item=mcq, text='Верно', is_correct=True)
        submission = start_submission(cls.student)
        submit_answers(submission, [
            {'item_id': item.id, 'text_answer': 'Меня зовут Иван'},
            {'item_id': mcq.id, 'option_id': cls.option.id},
        ])
        cls.submission = submission

    def setUp(self):
        self.client.force_login(self.admin)

    def test_invitation_list_and_detail_show_copy_button(self):
        response = self.client.get(reverse('admin:accounts_invitation_changelist'))
        self.assertContains(response, 'Скопировать ссылку')

        response = self.client.get(reverse('admin:accounts_invitation_change', args=[self.invitation.pk]))
        self.assertContains(response, str(self.invitation.token))

    def test_student_list_shows_status_and_progress(self):
        response = self.client.get(reverse('admin:accounts_student_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'На проверке')

    def test_student_card_renders_final_test_answers_inline(self):
        response = self.client.get(reverse('admin:accounts_student_change', args=[self.student.pk]))
        self.assertContains(response, 'Меня зовут Иван')
        self.assertContains(response, 'Расскажи о себе')

    def test_submission_page_renders(self):
        response = self.client.get(reverse('admin:finaltest_finaltestsubmission_change', args=[self.submission.pk]))
        self.assertContains(response, 'Меня зовут Иван')

    def test_bulk_action_sets_status(self):
        response = self.client.post(reverse('admin:accounts_student_changelist'), {
            'action': 'mark_needs_rework',
            '_selected_action': [self.student.pk],
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.NEEDS_REWORK)

    def test_dashboard_lists_students_waiting_for_review(self):
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ждут проверки')
        self.assertContains(response, 'Иван Иванов')
        self.assertContains(response, reverse('admin:accounts_invitation_add'))

    def test_detail_buttons_set_status_and_redirect_back_to_card(self):
        for url_name, expected in [
            ('admin:accounts_student_approve_detail', Student.Status.APPROVED),
            ('admin:accounts_student_rework_detail', Student.Status.NEEDS_REWORK),
            ('admin:accounts_student_reject_detail', Student.Status.REJECTED),
        ]:
            response = self.client.get(reverse(url_name, args=[self.student.pk]))
            self.assertRedirects(
                response, reverse('admin:accounts_student_change', args=[self.student.pk]),
            )
            self.student.refresh_from_db()
            self.assertEqual(self.student.status, expected)

    def test_user_and_group_pages_open(self):
        self.assertEqual(self.client.get(reverse('admin:auth_user_changelist')).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:auth_group_changelist')).status_code, 200)

    def test_module_admin_page_shows_learning_steps_inline(self):
        module = Module.objects.create(order=1, title='Модуль админки')
        ModuleStep.objects.create(module=module, order=1, kind='action', title='Задание для теста админки')
        response = self.client.get(reverse('admin:onboarding_module_change', args=[module.pk]))
        self.assertContains(response, 'Задание для теста админки')
        self.assertContains(response, 'Шаги обучения')
        self.assertEqual(self.client.get(reverse('admin:onboarding_module_changelist')).status_code, 200)

    def test_student_card_shows_step_notes(self):
        module = Module.objects.create(order=1, title='Модуль заметок')
        step = ModuleStep.objects.create(module=module, kind='action', title='Задание с заметкой', requires_note=True)
        set_step_progress(self.student, step, done=True, note='Заметка стажёра про звонок')
        response = self.client.get(reverse('admin:accounts_student_change', args=[self.student.pk]))
        self.assertContains(response, 'Заметка стажёра про звонок')

    def test_revoke_action_blocks_registration_link(self):
        self.client.post(reverse('admin:accounts_invitation_changelist'), {
            'action': 'revoke_invitations',
            '_selected_action': [self.invitation.pk],
        })
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, Invitation.Status.REVOKED)

        anonymous = self.client_class()
        response = anonymous.get(self.invitation.get_absolute_url())
        self.assertRedirects(response, reverse('accounts:login'))


class StudentModulePageTests(TestCase):
    def setUp(self):
        user = User.objects.create_user('learner', first_name='Анна', password='pass12345')
        self.student = Student.objects.create(user=user)
        self.module = Module.objects.create(order=1, title='Модуль 1')
        self.q1 = ModuleQuestion.objects.create(module=self.module, text='Вопрос 1', order=1)
        self.q1_ok = ModuleAnswerOption.objects.create(question=self.q1, text='Да', is_correct=True)
        self.q1_bad = ModuleAnswerOption.objects.create(question=self.q1, text='Нет', is_correct=False)
        self.q2 = ModuleQuestion.objects.create(module=self.module, text='Вопрос 2', order=2)
        self.q2_ok = ModuleAnswerOption.objects.create(question=self.q2, text='Да', is_correct=True)
        self.q2_bad = ModuleAnswerOption.objects.create(question=self.q2, text='Нет', is_correct=False)
        self.client.force_login(user)
        self.url = reverse('onboarding:module_quiz', args=[self.module.pk])

    def test_failed_attempt_redirects_and_page_marks_only_wrong_questions_keeping_selection(self):
        response = self.client.post(self.url, {
            f'question_{self.q1.id}': self.q1_ok.id,
            f'question_{self.q2.id}': self.q2_bad.id,
        })
        self.assertRedirects(response, self.url)  # обновление страницы не повторит отправку формы

        response = self.client.get(self.url)
        rows = response.context['question_rows']
        self.assertFalse(rows[0]['is_wrong'])
        self.assertTrue(rows[1]['is_wrong'])
        self.assertTrue(next(o for o in rows[0]['options'] if o['option'] == self.q1_ok)['checked'])
        self.assertTrue(next(o for o in rows[1]['options'] if o['option'] == self.q2_bad)['checked'])
        self.assertEqual(response.context['failed_attempt'].correct_count, 1)

    def test_refreshing_after_failed_attempt_does_not_log_another_attempt(self):
        self.client.post(self.url, {f'question_{self.q1.id}': self.q1_bad.id, f'question_{self.q2.id}': self.q2_bad.id})
        for _ in range(3):
            self.client.get(self.url)
        self.assertEqual(self.module.attempts.filter(student=self.student).count(), 1)

    def test_wrong_mark_disappears_after_changing_that_answer(self):
        self.client.post(self.url, {f'question_{self.q1.id}': self.q1_ok.id, f'question_{self.q2.id}': self.q2_bad.id})
        self.client.post(reverse('onboarding:module_draft', args=[self.module.pk]),
                         data={'answers': {str(self.q2.id): self.q2_ok.id}}, content_type='application/json')
        response = self.client.get(self.url)
        self.assertFalse(any(r['is_wrong'] for r in response.context['question_rows']))
        self.assertIsNone(response.context['failed_attempt'])

    def test_all_correct_redirects_to_dashboard(self):
        response = self.client.post(self.url, {
            f'question_{self.q1.id}': self.q1_ok.id,
            f'question_{self.q2.id}': self.q2_ok.id,
        })
        self.assertRedirects(response, reverse('onboarding:dashboard'))

    def test_garbage_answer_value_does_not_crash(self):
        response = self.client.post(self.url, {
            f'question_{self.q1.id}': 'abc',
            f'question_{self.q2.id}': self.q2_ok.id,
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.module.attempts.get(student=self.student).correct_count, 1)

    def test_dashboard_shows_next_step(self):
        response = self.client.get(reverse('onboarding:dashboard'))
        self.assertContains(response, 'Следующий шаг')
        self.assertEqual(response.context['d']['current_module'], self.module)
