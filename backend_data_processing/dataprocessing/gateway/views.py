import logging
from datetime import datetime, timezone

import requests
from django.db import DatabaseError, transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema

from gateway.serializers import GatewayPingsSerializer
from gateway.handle_views import get_patient_id_from_mac_id, update_application_last_connection, store_gateway_ping


class GatewayPingView(APIView):
    """
        Handles gateway ping events from devices.
        Updates patient connection timestamps and logs ping data for compliance tracking.
    """
    # authentication_classes = (DataProcessAuthentication,)
    authentication_classes = ()
    permission_classes = ()

    @swagger_auto_schema(
        request_body=GatewayPingsSerializer,
        responses={200: "Gateway ping successfully processed."}
    )
    def post(self, request, *args, **kwargs):
        serializer_var = GatewayPingsSerializer(data=request.data)
        serializer_var.is_valid(raise_exception=True)
        data = serializer_var.validated_data

        auth_header = request.headers.get("Authorization", "")
        bearer_token = None
        if auth_header.startswith("Bearer "):
            bearer_token = auth_header
        elif auth_header:
            bearer_token = f"Bearer {auth_header}"

        mac_gateway = data.get("gateway_mac")
        patient_id = data.get("patient_id")
        fw_version = data.get("fw_version")
        source = data.get("source")

        last_connection_time = (
            datetime.now(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        )
        last_connection_time_obj = datetime.strptime(
            last_connection_time, "%Y-%m-%dT%H:%M:%S.%fZ"
        ).replace(tzinfo=timezone.utc)

        try:
            if patient_id is None:
                patient_response = get_patient_id_from_mac_id(gateway_mac=mac_gateway)
                patient_response.raise_for_status()
                patient_id = patient_response.json().get("patientId")
            else:
                response = update_application_last_connection(
                    bearer_token=bearer_token,
                    patient_id=patient_id,
                    last_connection_time=last_connection_time,
                    fw_version=fw_version,
                )
                response.raise_for_status()

            response = store_gateway_ping(
                gateway_mac=mac_gateway,
                ping_timestamp=last_connection_time_obj,
                source=source,
                user_id=patient_id,
            )

            return response
        
        except requests.exceptions.RequestException as req_err:
            logging.error(f"[GatewayPing] Network error for mac : {mac_gateway}: {req_err}")
            return Response({
                "status_code": 502,
                "message": "Network error while processing gateway ping.",
                "error": str(req_err),
            }, status=status.HTTP_502_BAD_GATEWAY)

        except DatabaseError as db_err:
            logging.error(f"[GatewayPing] Database error for mac={mac_gateway}: {db_err}")
            return Response({
                "status_code": 500,
                "message": "Database error while saving gateway ping.",
                "error": str(db_err),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as err:
            logging.exception(f"[GatewayPing] Unexpected error for mac={mac_gateway}: {err}")
            return Response({
                "status_code": 500,
                "message": "Unexpected error occurred.",
                "error": str(err),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
