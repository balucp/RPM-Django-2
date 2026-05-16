import requests
import logging

from rest_framework.response import Response
from rest_framework import status

from dataprocessing import lib_settings as settings
from data_app import lib_update_compliance as compliance
from gateway.models import GatewayPings


def get_patient_id_from_mac_id(gateway_mac):
    """
        Fetch the patient ID assigned to a given gateway MAC address.

        Args:
            gateway_mac (str): The MAC address of the gateway.

        Returns:
            Response: The HTTP response object from the backend API.
    """

    url = f'{settings.backend_url}/api/gateway/assigned-patient/{gateway_mac}'
    headers = {
        'Content-Type': 'application/json',
        'auth-token': settings.backend_auth_key,
    }

    patient_response = requests.request(
        method='GET', url=url, headers=headers, timeout=5)
    logging.info("get_patient_id_from_mac_id response: %s", patient_response.json())
    return patient_response


def update_application_last_connection(bearer_token, patient_id, last_connection_time, fw_version):
    """
        Update the backend with the gateway's last connection time and firmware version.

        Args:
            bearer_token (str): The Bearer token.
            patient_id (str): The ID of the assigned patient.
            last_connection_time (str): The last connection timestamp (ISO 8601 format).
            fw_version (str): The firmware version of the gateway.

        Returns:
            Response: The HTTP response object from the backend API.
    """
        
    url = f'{settings.backend_url}/api/gateway/app-mode/last-connection-time'
    data = {
        'patientId': patient_id,
        'lastConnectionTime': last_connection_time,
        'fwVersion': fw_version
    }

    headers = {
        'Content-Type': 'application/json',
        'Authorization': bearer_token,
    }
    last_connection_time_response = requests.request(
        method='POST', url=url, headers=headers, json=data, timeout=5)
    logging.info("update_application_last_connection response: %s", last_connection_time_response.json())
    return last_connection_time_response

def store_gateway_ping(gateway_mac, ping_timestamp, source, user_id):
    """
        Store a gateway ping event and update the compliance cache.
    """

    try:
        logging.info(
            f"[GatewayPing] Creating ping record MAC : {gateway_mac}, UserID: {user_id}, "
            f"Source: {source}, Timestamp: {ping_timestamp}"
        )

        gateway_ping = GatewayPings.objects.create(
            gateway_mac=gateway_mac,
            ping_timestamp=ping_timestamp,
            user_id=user_id,
            source=source,
        )

        compliance.cache_table_update(
            gateway_ping.user_id,
            gateway_ping.ping_timestamp,
            "datetime_gateway_sent",
        )

        return Response({
            "status_code": 200,
            "message": "Gateway ping successfully processed.",
            "error": None,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logging.error(f"[GatewayPing] Error storing gateway ping for mac : {gateway_mac}, {e}")
        raise
