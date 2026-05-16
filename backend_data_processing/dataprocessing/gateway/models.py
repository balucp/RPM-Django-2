from django.db import models

class GatewayPings(models.Model):
    user_id = models.IntegerField(null=True, blank=True)
    gateway_mac = models.CharField(max_length=100, null=True, blank=True)
    source = models.CharField(max_length=100, null=True, blank=True)
    ping_timestamp = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.user_id}-{self.source}-{self.gateway_mac}"

    class Meta:
        verbose_name_plural = "Gateway pings"
