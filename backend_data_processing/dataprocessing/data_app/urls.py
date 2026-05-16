from django.urls import path
from rest_framework import routers
from .views import *

router = routers.SimpleRouter()


urlpatterns = [
    path('health_check', HealthCheckView.as_view(), name='health_check'),
    path('upload', UploadView.as_view()),
    path('query/spot', QuerySpotView.as_view()),
    path('query/trends', QueryTrendView.as_view()),
    path('query/list', QueryPatientListView.as_view()),
    path('query/spot/emr', QueryMonitoringDataView.as_view()),
    path('update_cache', UpdateCacheView.as_view()),
    path('query/data_syncing/trends', QueryDatasyncingtrendView.as_view()),
    path('export/processed', NewExportView.as_view()),
    # path('export/processed', ExportView.as_view()),
    path("submit-health-input", HealthDataView.as_view()),
    path("processing", ProcessInProgressListView.as_view()),
    path("query/spot/bp-device", SpotBPDeviceReadingsView.as_view()),
    path("vitals/readings", VitalReadingsListView.as_view()),
    path("data/other/bp-device", BPDeviceDataSubmissionView.as_view()),
    path("data/emr", EMRDataSUbmissionView.as_view()),
    path("api/dashboard/list", PatientListCacheView.as_view()),
    path("api/staging/process", StagingProcessManualView.as_view()),

]
urlpatterns.extend(router.urls)
