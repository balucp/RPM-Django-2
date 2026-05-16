from __future__ import absolute_import
import os
from celery import Celery
from django.conf import settings

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dataprocessing.settings')
app = Celery('dataprocessing')

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

app.conf.update(
    BROKER_URL=settings.CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND=settings.CELERY_RESULT_BACKEND,
    CELERY_ACCEPT_CONTENT=['json'],
    CELERY_TASK_SERIALIZER='json',
    CELERY_RESULT_SERIALIZER='json',
    CELERY_TIMEZONE='UTC')


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))