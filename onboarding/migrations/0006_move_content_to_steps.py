from django.db import migrations


def module_content_to_steps(apps, schema_editor):
    """Видео и конспект, которые раньше лежали в самом модуле, становятся первыми шагами обучения."""
    Module = apps.get_model('onboarding', 'Module')
    ModuleStep = apps.get_model('onboarding', 'ModuleStep')
    for module in Module.objects.all():
        order = 1
        if module.youtube_id or module.youtube_id_uz:
            ModuleStep.objects.create(
                module=module, order=order, kind='video', title='Видео урока', title_uz='Dars videosi',
                youtube_id=module.youtube_id, youtube_id_uz=module.youtube_id_uz,
            )
            order += 1
        if module.text_content or module.text_content_uz:
            ModuleStep.objects.create(
                module=module, order=order, kind='text', title='Конспект', title_uz='Konspekt',
                body=module.text_content, body_uz=module.text_content_uz,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('onboarding', '0005_modulestep_stepprogress'),
    ]

    operations = [
        migrations.RunPython(module_content_to_steps, migrations.RunPython.noop),
    ]
