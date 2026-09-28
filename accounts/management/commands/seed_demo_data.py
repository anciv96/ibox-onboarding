from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Invitation, Student
from finaltest.models import FinalTestAnswer, FinalTestItem, FinalTestOption, FinalTestSubmission
from onboarding.models import Module, ModuleAnswerOption, ModuleQuestion, ModuleStep
from onboarding.services import set_step_progress, submit_module_attempt

User = get_user_model()

UZ = {
    'Знакомство с IBOX и Sales Doctor': 'IBOX va Sales Doctor bilan tanishuv',
    'Этапы продажи и скрипт звонка': 'Sotuv bosqichlari va qoʻngʻiroq skripti',
    'Работа с возражениями': 'Eʼtirozlar bilan ishlash',
    'Что такое IBOX?': 'IBOX nima?',
    'Система складского учёта': 'Ombor hisobi tizimi',
    'CRM для продаж': 'Sotuv uchun CRM',
    'Бухгалтерский сервис': 'Buxgalteriya xizmati',
    'Кто целевой клиент IBOX?': 'IBOXning maqsadli mijozi kim?',
    'Частные лица': 'Jismoniy shaxslar',
    'B2B-компании со складом': 'Omborga ega B2B kompaniyalar',
    'Государственные школы': 'Davlat maktablari',
    'Что делаем на первом звонке в первую очередь?': 'Birinchi qoʻngʻiroqda avvalo nima qilamiz?',
    'Сразу называем цену': 'Darhol narxni aytamiz',
    'Выясняем текущую ситуацию клиента': 'Mijozning hozirgi holatini aniqlaymiz',
    'Отправляем договор': 'Shartnoma yuboramiz',
    'Сколько основных этапов продажи в нашем скрипте?': 'Skriptimizda sotuvning nechta asosiy bosqichi bor?',
    'Что означает возражение клиента?': 'Mijozning eʼtirozi nimani anglatadi?',
    'Клиент точно не купит': 'Mijoz albatta sotib olmaydi',
    'Клиенту нужно больше информации/уверенности': 'Mijozga koʻproq maʼlumot/ishonch kerak',
    'Что в первую очередь важно выяснить у клиента на первом звонке?': 'Birinchi qoʻngʻiroqda mijozdan avvalo nimani aniqlash muhim?',
    'Текущую ситуацию со складским учётом': 'Ombor hisobidagi hozirgi vaziyatni',
    'Бюджет на маркетинг': 'Marketing byudjetini',
    'Имя директора': 'Direktorning ismini',
    'Возражение клиента чаще всего означает:': 'Mijozning eʼtirozi koʻpincha quyidagini anglatadi:',
    'Клиенту нужно больше уверенности/информации': 'Mijozga koʻproq ishonch/maʼlumot kerak',
    'Опиши своими словами, чем IBOX полезен компании с 3 складами и ручным учётом в Excel.': 'IBOX 3 ta omborga ega va Excelʼda qoʻlda hisob yuritadigan kompaniyaga qanday foyda berishini oʻz soʻzlaring bilan tasvirla.',
    'Расскажи, как ты будешь готовиться к первому звонку с новым лидом.': 'Yangi lid bilan birinchi qoʻngʻiroqqa qanday tayyorlanishingni aytib ber.',
    'Клиент говорит: "У вас слишком дорого, у конкурентов дешевле." Как ответишь?': 'Mijoz aytadi: "Sizda juda qimmat, raqobatchilarda arzonroq." Qanday javob berasan?',
    'Клиент говорит: "Нам это не нужно, у нас и так всё работает в Excel." Как ответишь?': 'Mijoz aytadi: "Bizga bu kerak emas, bizda hammasi Excelʼda yaxshi ishlayapti." Qanday javob berasan?',
}
UZ_MODULE_TEXT = {
    1: (
        '# Mahsulot haqida\n\n'
        'IBOX — B2B kompaniyalar uchun ombor hisobi tizimi. Biz, Sales Doctor, uni oʻrta va yirik biznesga sotamiz.\n\n'
        '## Nimani bilish muhim\n'
        '- IBOX qoldiqlar hisobi, kirim/chiqim va inventarizatsiyani yopadi.\n'
        '- Maqsadli mijoz — 1 va undan ortiq omborga ega, Excelʼda qoʻlda hisob yurituvchi kompaniyalar.\n'
        '- Bizning ustunligimiz — tez joriy etish va jonli qoʻllab-quvvatlash.\n'
    ),
    2: (
        '# Sotuv bosqichlari\n\n'
        '1. Malakalash\n2. Taqdimot\n3. Eʼtirozlar bilan ishlash\n4. Yopish\n\n'
        'Birinchi qoʻngʻiroqda sotmaymiz, mijozning ogʻrigʻini aniqlaymiz: ombor hozir qanday yuritiladi.'
    ),
    3: (
        '# Eʼtirozlar — bu normal\n\n'
        'Eʼtiroz — qiziqish belgisi, rad etish emas. Asosiysi — bahslashmaslik, '
        'mijoz soʻzlari ortida nima turganini tushunish va qadriyatni koʻrsatish.'
    ),
}


# Дополнительные шаги обучения (кроме видео и конспекта, которые берутся из данных модуля)
EXTRA_STEPS = {
    1: [
        {
            'kind': 'action', 'title': 'Посмотри демо IBOX', 'title_uz': 'IBOX demosini koʻrib chiq',
            'body': 'Открой демо-версию IBOX и найди разделы «Остатки», «Приход» и «Инвентаризация». Убедись, что понимаешь, где что лежит.',
            'body_uz': 'IBOX demo versiyasini och va «Qoldiqlar», «Kirim» va «Inventarizatsiya» boʻlimlarini top. Qayerda nima turganini tushunganingga ishonch hosil qil.',
        },
        {
            'kind': 'action', 'requires_note': True, 'title': 'Объясни своими словами', 'title_uz': 'Oʻz soʻzlaring bilan tushuntir',
            'body': 'Напиши 1–2 предложения: чем IBOX лучше складского учёта в Excel?',
            'body_uz': '1–2 ta gap yoz: IBOX Excelʼdagi ombor hisobidan nimasi bilan yaxshi?',
        },
        {
            'kind': 'resource', 'is_required': False, 'title': 'Презентация IBOX для клиентов', 'title_uz': 'Mijozlar uchun IBOX taqdimoti',
            'body': 'Пример ссылки — замени на реальную презентацию.', 'body_uz': 'Havola namunasi — haqiqiy taqdimot bilan almashtiring.',
            'url': 'https://example.com/ibox-presentation',
        },
    ],
    2: [
        {
            'kind': 'action', 'title': 'Отрепетируй первый звонок', 'title_uz': 'Birinchi qoʻngʻiroqni mashq qil',
            'body': 'Позвони коллеге или наставнику и отрепетируй первые 2 минуты звонка по скрипту.',
            'body_uz': 'Hamkasbing yoki murabbiyga qoʻngʻiroq qilib, skript boʻyicha qoʻngʻiroqning dastlabki 2 daqiqasini mashq qil.',
        },
        {
            'kind': 'action', 'requires_note': True, 'title': 'Подготовь вопросы клиенту', 'title_uz': 'Mijozga savollar tayyorla',
            'body': 'Запиши 5 вопросов, которые задашь клиенту про его склад, чтобы выяснить боль.',
            'body_uz': 'Ogʻriqni aniqlash uchun mijozga uning ombori haqida beradigan 5 ta savolingni yoz.',
        },
    ],
    3: [
        {
            'kind': 'action', 'requires_note': True, 'title': 'Разбери три возражения', 'title_uz': 'Uchta eʼtirozni tahlil qil',
            'body': 'Выпиши три самых частых возражения клиентов и по одному ответу на каждое.',
            'body_uz': 'Mijozlarning eng koʻp uchraydigan uchta eʼtirozini va har biriga bittadan javobni yoz.',
        },
    ],
}


def uz(text):
    return UZ.get(text, '')


class Command(BaseCommand):
    help = 'Создаёт тестовые данные: админа, модули с вопросами, финальный тест и учеников на разных стадиях.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--content-only', action='store_true',
            help='Создать только тестовые модули и финальный тест — без админа с известным паролем и без демо-учеников.',
        )
        parser.add_argument(
            '--reset', action='store_true',
            help='Удалить существующие модули/тест/учеников перед созданием заново.',
        )

    def handle(self, *args, **options):
        if options['reset']:
            self.stdout.write('Удаляю старые демо-данные...')
            Student.objects.all().delete()
            Invitation.objects.all().delete()
            Module.objects.all().delete()
            FinalTestItem.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()

        with transaction.atomic():
            modules = self._create_modules()
            self._create_final_test()
            if not options['content_only']:
                self._create_admin()
                self._create_demo_students(modules)

        self.stdout.write(self.style.SUCCESS('Готово. Тестовые данные созданы.'))

    def _create_admin(self):
        if User.objects.filter(is_superuser=True).exists():
            return
        User.objects.create_superuser(username='admin', email='admin@salesdoctor.local', password='admin12345')
        self.stdout.write(self.style.WARNING(
            'Создан админ: логин admin / пароль admin12345 — смени пароль после первого входа.'
        ))

    def _create_modules(self):
        if Module.objects.exists():
            self.stdout.write('Модули уже есть, пропускаю.')
            return list(Module.objects.order_by('order'))

        modules_data = [
            {
                'order': 1,
                'title': 'Знакомство с IBOX и Sales Doctor',
                'youtube_id': 'dQw4w9WgXcQ',
                'text_content': (
                    '# О продукте\n\n'
                    'IBOX — система складского учёта для B2B-компаний. Мы, Sales Doctor, '
                    'продаём её среднему и крупному бизнесу.\n\n'
                    '## Что важно знать\n'
                    '- IBOX закрывает учёт остатков, приход/расход, инвентаризацию.\n'
                    '- Целевой клиент — компании с 1+ складом и ручным Excel-учётом.\n'
                    '- Наше УТП — быстрое внедрение и живая поддержка.\n'
                ),
                'questions': [
                    {
                        'text': 'Что такое IBOX?',
                        'options': [
                            ('Система складского учёта', True),
                            ('CRM для продаж', False),
                            ('Бухгалтерский сервис', False),
                        ],
                    },
                    {
                        'text': 'Кто целевой клиент IBOX?',
                        'options': [
                            ('Частные лица', False),
                            ('B2B-компании со складом', True),
                            ('Государственные школы', False),
                        ],
                    },
                ],
            },
            {
                'order': 2,
                'title': 'Этапы продажи и скрипт звонка',
                'youtube_id': 'dQw4w9WgXcQ',
                'text_content': (
                    '# Этапы продажи\n\n'
                    '1. Квалификация\n2. Презентация\n3. Работа с возражениями\n4. Закрытие\n\n'
                    'На первом звонке — не продаём, а выясняем боль клиента: как сейчас ведётся склад.'
                ),
                'questions': [
                    {
                        'text': 'Что делаем на первом звонке в первую очередь?',
                        'options': [
                            ('Сразу называем цену', False),
                            ('Выясняем текущую ситуацию клиента', True),
                            ('Отправляем договор', False),
                        ],
                    },
                    {
                        'text': 'Сколько основных этапов продажи в нашем скрипте?',
                        'options': [
                            ('2', False),
                            ('4', True),
                            ('7', False),
                        ],
                    },
                ],
            },
            {
                'order': 3,
                'title': 'Работа с возражениями',
                'youtube_id': 'dQw4w9WgXcQ',
                'text_content': (
                    '# Возражения — это нормально\n\n'
                    'Возражение — признак интереса, а не отказа. Главное — не спорить, '
                    'а понять, что стоит за словами клиента, и показать ценность.'
                ),
                'questions': [
                    {
                        'text': 'Что означает возражение клиента?',
                        'options': [
                            ('Клиент точно не купит', False),
                            ('Клиенту нужно больше информации/уверенности', True),
                        ],
                    },
                ],
            },
        ]

        modules = []
        for data in modules_data:
            module = Module.objects.create(
                order=data['order'], title=data['title'], title_uz=uz(data['title']),
            )
            self._create_steps(module, data)
            for q_order, q_data in enumerate(data['questions'], start=1):
                question = ModuleQuestion.objects.create(
                    module=module, text=q_data['text'], text_uz=uz(q_data['text']), order=q_order,
                )
                for text, is_correct in q_data['options']:
                    ModuleAnswerOption.objects.create(
                        question=question, text=text, text_uz=uz(text), is_correct=is_correct,
                    )
            modules.append(module)

        self.stdout.write(f'Создано модулей: {len(modules)}')
        return modules

    @staticmethod
    def _create_steps(module, data):
        order = 1
        ModuleStep.objects.create(
            module=module, order=order, kind=ModuleStep.Kind.VIDEO,
            title='Видео урока', title_uz='Dars videosi', youtube_id=data['youtube_id'],
        )
        order += 1
        ModuleStep.objects.create(
            module=module, order=order, kind=ModuleStep.Kind.TEXT, title='Конспект', title_uz='Konspekt',
            body=data['text_content'], body_uz=UZ_MODULE_TEXT.get(data['order'], ''),
        )
        for extra in EXTRA_STEPS.get(data['order'], []):
            order += 1
            ModuleStep.objects.create(module=module, order=order, **extra)

    @staticmethod
    def _complete_steps(student, module):
        for step in module.steps.all():
            note = 'Демо-заметка: разобрался, всё понятно.' if step.requires_note else None
            set_step_progress(student, step, done=True, note=note)

    def _create_final_test(self):
        if FinalTestItem.objects.exists():
            self.stdout.write('Финальный тест уже есть, пропускаю.')
            return

        order = 1

        mcq_item = FinalTestItem.objects.create(
            type=FinalTestItem.Type.MCQ, order=order,
            prompt='Что в первую очередь важно выяснить у клиента на первом звонке?', prompt_uz=uz('Что в первую очередь важно выяснить у клиента на первом звонке?'),
        )
        FinalTestOption.objects.create(item=mcq_item, text='Текущую ситуацию со складским учётом', text_uz=uz('Текущую ситуацию со складским учётом'), is_correct=True)
        FinalTestOption.objects.create(item=mcq_item, text='Бюджет на маркетинг', text_uz=uz('Бюджет на маркетинг'), is_correct=False)
        FinalTestOption.objects.create(item=mcq_item, text='Имя директора', text_uz=uz('Имя директора'), is_correct=False)
        order += 1

        mcq_item2 = FinalTestItem.objects.create(
            type=FinalTestItem.Type.MCQ, order=order,
            prompt='Возражение клиента чаще всего означает:', prompt_uz=uz('Возражение клиента чаще всего означает:'),
        )
        FinalTestOption.objects.create(item=mcq_item2, text='Клиент точно не купит', text_uz=uz('Клиент точно не купит'), is_correct=False)
        FinalTestOption.objects.create(item=mcq_item2, text='Клиенту нужно больше уверенности/информации', text_uz=uz('Клиенту нужно больше уверенности/информации'), is_correct=True)
        order += 1

        FinalTestItem.objects.create(
            type=FinalTestItem.Type.OPEN, order=order,
            prompt='Опиши своими словами, чем IBOX полезен компании с 3 складами и ручным учётом в Excel.', prompt_uz=uz('Опиши своими словами, чем IBOX полезен компании с 3 складами и ручным учётом в Excel.'),
        )
        order += 1

        FinalTestItem.objects.create(
            type=FinalTestItem.Type.OPEN, order=order,
            prompt='Расскажи, как ты будешь готовиться к первому звонку с новым лидом.', prompt_uz=uz('Расскажи, как ты будешь готовиться к первому звонку с новым лидом.'),
        )
        order += 1

        FinalTestItem.objects.create(
            type=FinalTestItem.Type.CASE, order=order,
            prompt='Клиент говорит: "У вас слишком дорого, у конкурентов дешевле." Как ответишь?', prompt_uz=uz('Клиент говорит: "У вас слишком дорого, у конкурентов дешевле." Как ответишь?'),
        )
        order += 1

        FinalTestItem.objects.create(
            type=FinalTestItem.Type.CASE, order=order,
            prompt='Клиент говорит: "Нам это не нужно, у нас и так всё работает в Excel." Как ответишь?', prompt_uz=uz('Клиент говорит: "Нам это не нужно, у нас и так всё работает в Excel." Как ответишь?'),
        )

        self.stdout.write(f'Создано элементов финального теста: {order}')

    @staticmethod
    def _answer_module(student, module, correct):
        answers = {}
        for question in module.questions.all():
            options = question.options.all()
            option = next((o for o in options if o.is_correct == correct), options[0])
            answers[question.id] = option.id
        return submit_module_attempt(student, module, answers)

    def _pass_module(self, student, module, fail_first=False):
        if fail_first:
            self._answer_module(student, module, correct=False)
        self._answer_module(student, module, correct=True)

    def _create_demo_students(self, modules):
        if Student.objects.exists():
            self.stdout.write('Демо-ученики уже есть, пропускаю.')
            return
        if not modules:
            modules = list(Module.objects.order_by('order'))

        # 1. Приглашение без регистрации — демонстрирует именную ссылку
        Invitation.objects.create(full_name='Азиз Каримов', status=Invitation.Status.PENDING)

        # 2. Ученица в процессе: 1 модуль пройден, на втором
        inv2 = Invitation.objects.create(
            full_name='Дилноза Юсупова', status=Invitation.Status.USED,
        )
        user2 = User.objects.create_user(
            username='dilnoza', first_name='Дилноза', last_name='Юсупова', password='demo12345',
        )
        student2 = Student.objects.create(
            user=user2, invitation=inv2, status=Student.Status.IN_PROGRESS,
        )
        if modules:
            self._complete_steps(student2, modules[0])
            self._pass_module(student2, modules[0], fail_first=True)
            if len(modules) > 1:  # на втором модуле выполнена только часть шагов — тест ещё закрыт
                for step in list(modules[1].steps.all())[:2]:
                    set_step_progress(student2, step, done=True)

        # 3. Ученик, сдавший финальный тест — ждёт проверки админом
        inv3 = Invitation.objects.create(
            full_name='Жасур Тошматов', status=Invitation.Status.USED,
        )
        user3 = User.objects.create_user(
            username='jasur', first_name='Жасур', last_name='Тошматов', password='demo12345',
        )
        student3 = Student.objects.create(
            user=user3, invitation=inv3, status=Student.Status.PENDING_REVIEW,
        )
        for index, module in enumerate(modules):
            self._complete_steps(student3, module)
            self._pass_module(student3, module, fail_first=(index == 1))

        submission = FinalTestSubmission.objects.create(student=student3, attempt_number=1)
        from django.utils import timezone
        correct_count = 0
        mcq_total = 0
        for item in FinalTestItem.objects.all():
            if item.type == FinalTestItem.Type.MCQ:
                mcq_total += 1
                correct_option = item.options.filter(is_correct=True).first()
                correct_count += 1
                FinalTestAnswer.objects.create(
                    submission=submission, item=item, selected_option=correct_option, is_correct=True,
                )
            else:
                FinalTestAnswer.objects.create(
                    submission=submission, item=item,
                    text_answer='Демо-ответ ученика: подробное объяснение того, как я бы ответил клиенту.',
                )
        submission.submitted_at = timezone.now()
        submission.mcq_score_percent = round(correct_count * 100 / mcq_total) if mcq_total else None
        submission.save(update_fields=['submitted_at', 'mcq_score_percent'])

        self.stdout.write('Создано демо-учеников: 3 (включая неиспользованное приглашение)')
