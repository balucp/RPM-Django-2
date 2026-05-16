from django.contrib import admin
from .models import *


class GatewayPingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_id',)
    search_fields = ('id', 'user_id',)

admin.site.register(GatewayPings, GatewayPingsAdmin)
