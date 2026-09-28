from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Student
from practice.models import PracticeAnswer, PracticeOption, PracticeQuestion
from practice.services import new_round, stats

User = get_user_model()


def make_question(n, category='cases', options=3):
    question = PracticeQuestion.objects.create(category=category, prompt=f'Вопрос {n}', explanation=f'Разбор {n}')
    for k in range(options):
        PracticeOption.objects.create(question=question, text=f'Вариант {k}', is_correct=(k == 0))
    return question


class PracticeBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='trainee', password='pass12345')
        self.student = Student.objects.create(user=self.user)
        self.client.login(username='trainee', password='pass12345')
        self.questions = [make_question(n, 'cases' if n % 2 else 'myth') for n in range(25)]


class RoundSelectionTests(PracticeBase):
    def test_round_has_ten_random_questions(self):
        state = new_round(self.student)
        self.assertEqual(len(state['ids']), 10)
        self.assertEqual(len(set(state['ids'])), 10)

    def test_unseen_questions_come_first_then_wrong_ones(self):
        seen = self.questions[:20]
        for i, question in enumerate(seen):
            PracticeAnswer.objects.create(student=self.student, question=question, is_correct=(i >= 3))
        state = new_round(self.student)
        unseen = {q.id for q in self.questions[20:]}
        wrong = {q.id for q in seen[:3]}
        self.assertTrue(unseen <= set(state['ids']))
        self.assertTrue(wrong <= set(state['ids']))

    def test_unpublished_questions_are_never_offered(self):
        PracticeQuestion.objects.filter(pk=self.questions[0].pk).update(is_published=False)
        for _ in range(5):
            self.assertNotIn(self.questions[0].pk, new_round(self.student)['ids'])

    def test_category_filter(self):
        state = new_round(self.student, 'myth')
        self.assertTrue(all(PracticeQuestion.objects.get(pk=i).category == 'myth' for i in state['ids']))

    def test_empty_pool_gives_no_round(self):
        PracticeQuestion.objects.all().delete()
        self.assertIsNone(new_round(self.student))


class PracticeFlowTests(PracticeBase):
    def _start(self, category=''):
        return self.client.post(reverse('practice:start'), {'category': category})

    def test_lobby_shows_stats_and_games(self):
        response = self.client.get(reverse('practice:lobby'))
        self.assertContains(response, 'Кейсы: бизнес')
        self.assertContains(response, 'Смешанный раунд')

    def test_full_round_records_answers_and_shows_summary(self):
        self.assertRedirects(self._start(), reverse('practice:play'))
        for step in range(10):
            page = self.client.get(reverse('practice:play'))
            self.assertContains(page, f'Вопрос {step + 1} из 10')
            question = page.context['question']
            right = question.options.get(is_correct=True)
            self.client.post(reverse('practice:play'), {'action': 'answer', 'option': right.id})
            feedback = self.client.get(reverse('practice:play'))
            self.assertContains(feedback, 'Верно!')
            self.assertContains(feedback, f'Разбор {question.prompt.split()[-1]}')
            self.client.post(reverse('practice:play'), {'action': 'next'})
        summary = self.client.get(reverse('practice:play'))
        self.assertContains(summary, 'Итоги раунда')
        self.assertEqual(summary.context['correct'], 10)
        self.assertEqual(PracticeAnswer.objects.filter(student=self.student).count(), 10)

    def test_answer_cannot_be_changed_or_double_counted(self):
        self._start()
        page = self.client.get(reverse('practice:play'))
        question = page.context['question']
        first = question.options.get(is_correct=True).id
        wrong = question.options.filter(is_correct=False).first().id
        self.client.post(reverse('practice:play'), {'action': 'answer', 'option': first})
        self.client.post(reverse('practice:play'), {'action': 'answer', 'option': wrong})
        self.assertEqual(PracticeAnswer.objects.filter(student=self.student).count(), 1)
        self.assertTrue(PracticeAnswer.objects.get().is_correct)

    def test_foreign_option_is_ignored(self):
        self._start()
        question = self.client.get(reverse('practice:play')).context['question']
        other = PracticeOption.objects.exclude(question=question).first()
        self.client.post(reverse('practice:play'), {'action': 'answer', 'option': other.id})
        self.assertEqual(PracticeAnswer.objects.count(), 0)

    def test_wrong_answer_is_listed_in_summary(self):
        self._start()
        for _ in range(10):
            question = self.client.get(reverse('practice:play')).context['question']
            wrong = question.options.filter(is_correct=False).first()
            self.client.post(reverse('practice:play'), {'action': 'answer', 'option': wrong.id})
            self.client.post(reverse('practice:play'), {'action': 'next'})
        summary = self.client.get(reverse('practice:play'))
        self.assertEqual(summary.context['correct'], 0)
        self.assertEqual(len(summary.context['missed']), 10)
        self.assertContains(summary, 'Разбор ошибок')

    def test_stats_count_mastered_by_latest_answer(self):
        q = self.questions[0]
        PracticeAnswer.objects.create(student=self.student, question=q, is_correct=False)
        PracticeAnswer.objects.create(student=self.student, question=q, is_correct=True)
        data = stats(self.student)
        self.assertEqual((data['answered'], data['accuracy'], data['mastered']), (2, 50, 1))

    def test_requires_login_and_student_profile(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('practice:lobby')).status_code, 302)
        staff = User.objects.create_user(username='boss', password='pass12345', is_staff=True)
        self.client.login(username='boss', password='pass12345')
        self.assertRedirects(self.client.get(reverse('practice:lobby')), '/admin/', fetch_redirect_response=False)

    def test_practice_does_not_touch_onboarding_progress(self):
        from onboarding.progress import overall_progress
        before = overall_progress(self.student)['percent']
        self._start()
        question = self.client.get(reverse('practice:play')).context['question']
        self.client.post(reverse('practice:play'), {'action': 'answer', 'option': question.options.get(is_correct=True).id})
        self.assertEqual(overall_progress(self.student)['percent'], before)
