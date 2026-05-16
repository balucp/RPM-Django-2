from django.apps import AppConfig


class DataappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'data_app'

    def ready(self) -> None:
        import data_app.signals
