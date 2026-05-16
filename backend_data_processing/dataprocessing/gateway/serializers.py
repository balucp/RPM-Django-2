from rest_framework import serializers

class GatewayPingsSerializer(serializers.Serializer):
    patient_id = serializers.IntegerField(required=False, allow_null=True)
    # last_connection_time = serializers.DateTimeField(
    #     required=True, allow_null=False)
    gateway_mac = serializers.CharField(required=True, allow_null=False)
    fw_version = serializers.CharField(required=False, allow_null=True)
    source = serializers.CharField(required=False, allow_null=True)
