import logging
import sys
import traceback
from data_app.models import SpotCache
from dataprocessing import lib_settings as settings

def spot_cache_update(item,source):

    try:
        query_items = SpotCache.objects.filter(user_id=item['user_id'], source=source)
        if query_items.count() >= settings.SPOT_CACHE_MAX_LEN:
            oldest = query_items.first()
            oldest.delete()
        item['source'] = source
        SpotCache.objects.create(**item)
        logging.info(f"Spot table updated   for user {item['user_id']}. Data is {item}")
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        err = "\n".join(traceback.format_exception(*sys.exc_info()))
        logging.error(f"Error in spot_cache_update(). Error : {err}")