from datetime import datetime
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import *

from .tasks import real_time_trigger
from data_app.lib_update_cache_incremental import update_cache

@receiver(post_save, sender=MetricMinutesCache)
def post_save_metric_minutes_cache(sender, instance, **kwargs):
    if not kwargs.get('raw'):
        real_time_trigger(instance.id)
    date_time = instance.date_time
    if isinstance(date_time, str):
        try:
            date_time = datetime.strptime(date_time, "%Y-%m-%dT%H:%M:%S")
        except Exception as e:
            logging.warning(
                "Failed parsing datetime with strptime for instance %s: %s",
                instance.id, str(e)
            )
    date_time_str = date_time.strftime("%Y-%m-%d %H:%M:%S")
    update_cache(instance.user_id, date_time_str)
