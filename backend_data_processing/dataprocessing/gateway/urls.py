from django.urls import path
from rest_framework import routers
from gateway.views import *

router = routers.SimpleRouter()


urlpatterns = [
    path('gateway/last-connection', GatewayPingView.as_view()),
]
urlpatterns.extend(router.urls)
