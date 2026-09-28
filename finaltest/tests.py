from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import Student
from finaltest.models import FinalTestItem, FinalTestOption
from finaltest.services import can_start_final_test, start_submission, submit_answers
from onboarding.models import Module, ModuleProgress

User = get_user_model()


class FinalTestGatingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='student3', password='pass12345')
        self.student = Student.objects.create(user=self.user)
        self.module1 = Module.objects.create(order=1, title='Модуль 1')
        self.module2 = Module.objects.create(order=2, title='Модуль 2')

    def test_cannot_start_before_modules_completed(self):
        self.assertFalse(can_start_final_test(self.student))

        ModuleProgress.objects.create(student=self.student, module=self.module1)
        self.assertFalse(can_start_final_test(self.student))

    def test_can_start_after_all_modules_completed(self):
        ModuleProgress.objects.create(student=self.student, module=self.module1)
        ModuleProgress.objects.create(student=self.student, module=self.module2)
        self.assertTrue(can_start_final_test(self.student))

    def test_cannot_retake_while_pending_review(self):
        ModuleProgress.objects.create(student=self.student, module=self.module1)
        ModuleProgress.objects.create(student=self.student, module=self.module2)
        submission = start_submission(self.student)
        submit_answers(submission, [])

        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.PENDING_REVIEW)
        self.assertFalse(can_start_final_test(self.student))

    def test_can_retake_after_admin_marks_needs_rework(self):
        ModuleProgress.objects.create(student=self.student, module=self.module1)
        ModuleProgress.objects.create(student=self.student, module=self.module2)
        submission = start_submission(self.student)
        submit_answers(submission, [])

        self.student.status = Student.Status.NEEDS_REWORK
        self.student.save(update_fields=['status'])

        self.assertTrue(can_start_final_test(self.student))

    def test_cannot_retake_after_approval(self):
        ModuleProgress.objects.create(student=self.student, module=self.module1)
        ModuleProgress.objects.create(student=self.student, module=self.module2)
        submission = start_submission(self.student)
        submit_answers(submission, [])

        self.student.status = Student.Status.APPROVED
        self.student.save(update_fields=['status'])

        self.assertFalse(can_start_final_test(self.student))

    def test_all_attempts_are_kept_not_only_latest(self):
        ModuleProgress.objects.create(student=self.student, module=self.module1)
        ModuleProgress.objects.create(student=self.student, module=self.module2)

        submission1 = start_submission(self.student)
        submit_answers(submission1, [])
        self.student.status = Student.Status.NEEDS_REWORK
        self.student.save(update_fields=['status'])

        submission2 = start_submission(self.student)
        submit_answers(submission2, [])

        self.assertEqual(self.student.final_submissions.count(), 2)
        self.assertEqual(submission1.attempt_number, 1)
        self.assertEqual(submission2.attempt_number, 2)


class FinalTestScoringTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='student4', password='pass12345')
        self.student = Student.objects.create(user=self.user)

        self.mcq = FinalTestItem.objects.create(type=FinalTestItem.Type.MCQ, prompt='Вопрос', order=1)
        self.correct_option = FinalTestOption.objects.create(item=self.mcq, text='Верно', is_correct=True)
        self.wrong_option = FinalTestOption.objects.create(item=self.mcq, text='Неверно', is_correct=False)

        self.open_item = FinalTestItem.objects.create(type=FinalTestItem.Type.OPEN, prompt='Опиши', order=2)

    def test_mcq_auto_scored_open_left_for_manual_review(self):
        submission = start_submission(self.student)
        submit_answers(submission, [
            {'item_id': self.mcq.id, 'option_id': self.correct_option.id},
            {'item_id': self.open_item.id, 'text_answer': 'Мой развёрнутый ответ'},
        ])

        submission.refresh_from_db()
        self.assertEqual(submission.mcq_score_percent, 100)

        open_answer = submission.answers.get(item=self.open_item)
        self.assertIsNone(open_answer.is_correct)
        self.assertIsNone(open_answer.ai_score)
        self.assertEqual(open_answer.text_answer, 'Мой развёрнутый ответ')

    def test_wrong_mcq_answer_scored_zero(self):
        submission = start_submission(self.student)
        submit_answers(submission, [
            {'item_id': self.mcq.id, 'option_id': self.wrong_option.id},
        ])

        submission.refresh_from_db()
        self.assertEqual(submission.mcq_score_percent, 0)


class FinalTestRandomSelectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='student5', password='pass12345')
        self.student = Student.objects.create(user=self.user)
        for n in range(30):
            item = FinalTestItem.objects.create(type=FinalTestItem.Type.MCQ, prompt=f'Вопрос {n}')
            for k in range(3):
                FinalTestOption.objects.create(item=item, text=f'В{k}', is_correct=(k == 0))
        for n in range(6):
            FinalTestItem.objects.create(type=FinalTestItem.Type.OPEN, prompt=f'Открытый {n}')

    def test_submission_gets_random_subset_of_configured_size(self):
        from django.test import override_settings
        with override_settings(FINAL_TEST_MCQ_COUNT=17, FINAL_TEST_OPEN_COUNT=3):
            submission = start_submission(self.student)
        self.assertEqual(len(submission.item_ids), 20)
        self.assertEqual(len(set(submission.item_ids)), 20)
        types = [FinalTestItem.objects.get(pk=i).type for i in submission.item_ids]
        self.assertEqual(types.count('mcq'), 17)
        self.assertEqual(types[-3:], ['open'] * 3)

    def test_draft_ignores_questions_outside_the_attempt(self):
        from finaltest.services import clean_final_answers, submission_items
        submission = start_submission(self.student)
        inside = submission_items(submission)[0]
        outside = FinalTestItem.objects.exclude(pk__in=submission.item_ids).first()
        cleaned = clean_final_answers(
            {str(inside.id): inside.options.first().id, str(outside.id): outside.options.first().id if outside.options.exists() else 1},
            submission,
        )
        self.assertEqual(list(cleaned), [inside.id])

    def test_option_order_is_stable_per_attempt(self):
        from finaltest.services import shuffled_options, submission_items
        submission = start_submission(self.student)
        item = submission_items(submission)[0]
        self.assertEqual(shuffled_options(submission, item), shuffled_options(submission, item))
