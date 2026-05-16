from django.contrib import admin
from .models import *

class DataProcessingAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_id', 'record_collected_by_sensor', 'record_received_by_gateway', 'record_server_received', 'date_time', 'sensor_onskin_status',)
    search_fields = ('id', 'user_id',)

class MetricMinutesCacheAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_id',)
    search_fields = ('id', 'user_id',)

class MetricCacheAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_id',)
    search_fields = ('id', 'user_id',)

class SpotCacheAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_id', 'sensor_onskin_status',)
    search_fields = ('id', 'user_id',)

class ApiDataSentOutAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_id',)
    search_fields = ('id', 'user_id',)

admin.site.register(DataProcessing, DataProcessingAdmin)
admin.site.register(MetricMinutesCache, MetricMinutesCacheAdmin)
admin.site.register(MetricDailyCache, MetricCacheAdmin)
admin.site.register(SpotCache, SpotCacheAdmin)
admin.site.register(ApiDataSentOut, ApiDataSentOutAdmin)
