from rest_framework import serializers

class UploadResponseSerializer(serializers.Serializer):
    userId = serializers.IntegerField()
    dateTimeGatewaySent = serializers.DateTimeField()
    dateTimeServerReceived = serializers.DateTimeField()