import requests
from rest_framework import authentication
from rest_framework import exceptions as rest_exception
from dataprocessing import lib_settings as settings


class DataProcessAuthentication(authentication.BaseAuthentication):

    def process_token(self, auth_header, request):
        auth_header_prefix = 'bearer'

        if len(auth_header) == 1 or len(auth_header) > 2:
            raise rest_exception.AuthenticationFailed(
                'Invalid Authorization header prefix, expecting: Bearer. <token>'
            )

        prefix = auth_header[0].decode('utf-8')
        token = auth_header[1].decode('utf-8')
        if prefix.lower() != auth_header_prefix:
            # The auth header prefix is not what we expected. Do not attempt to
            # authenticate.

            raise rest_exception.AuthenticationFailed(
                'Invalid Authorization header prefix, expecting: Bearer.'
            )

        return self._authenticate_token(prefix, token, request)

    def process_api_key(self, auth_header):
        if auth_header != settings.backend_auth_key:
            raise rest_exception.AuthenticationFailed(
                "Invalid x-api-key provided.")
        return None

    def process_referer_token(self, token):
        """
        Validate Referer token against allowed list in settings.
        """
        if token not in getattr(settings, "VALID_REFERER", []):
            raise rest_exception.AuthenticationFailed(
                "Invalid Referer key provided.")
        return None

    def extract_user_ids(self,request):
        """Extract user IDs from query parameters."""
        for key in ("list_of_ids", "id", "list_of_id", "user_id"):
            if key in request.query_params:
                values = request.query_params .get(key)
                return values if isinstance(values, list) else values.split(",")
        return []

    def _authenticate_token(self, prefix, token,request):
        """
        Try to authenticate token by calling data service and verifying validity of the token.
        """
        user_ids = self.extract_user_ids(request)
        params = {"patientId": ",".join(map(str, user_ids))} if user_ids else {}
        auth_url = f'{settings.backend_url}/api/data-server/verify/user'
        response = requests.request('GET', auth_url, headers={
                                    'Authorization': f'{prefix.capitalize()} {token}'}, timeout=5, params=params)
        if response.status_code != requests.codes.ok:
            try:
                error_data = response.json()
            except ValueError:
                error_data = {
                    "statusCode": response.status_code,
                    "message": response.text or "Authentication failed",
                    "path": auth_url,
                }
            filtered_error = {
                "statusCode": error_data.get("statusCode", response.status_code),
                "message": error_data.get("message", "Authentication failed"),
                "timestamp": error_data.get("timestamp"),
            }
            raise rest_exception.AuthenticationFailed(filtered_error)
        return None

    def authenticate(self, request):
        """
            Authenticate request via:
            1. Authorization Bearer token
            2. X-API-KEY
            3. Referer token
        """
        
        auth_header = authentication.get_authorization_header(request)
        if auth_header:
            auth_source = "authorization"
            auth_header = auth_header.split()
        elif request.META.get("HTTP_X_API_KEY"):
            auth_source = "api_key"
            auth_header = request.META.get("HTTP_X_API_KEY")
        elif request.META.get("HTTP_REFERER"):
            auth_source = "referer"
            auth_header = request.META.get("HTTP_REFERER")
        else:
            raise rest_exception.AuthenticationFailed(
                "Invalid header format, expecting: Authorization Bearer <token>, X-API-KEY, or Referer."
            )

        if auth_source == "authorization":
            return self.process_token(auth_header, request)
        elif auth_source == "referer":
            return self.process_referer_token(auth_header)
        else:
            return self.process_api_key(auth_header)


class GatewayAuthentication(authentication.BaseAuthentication):
    """
    Custom authentication class to validate the Referer header.
    """

    def authenticate(self, request):
        try:
            VALID_REFERER = settings.VALID_REFERER
            auth_key = request.headers.get('Referer', None)
            if not auth_key or auth_key not in VALID_REFERER:
                raise rest_exception.AuthenticationFailed('Client is not authorized to perform this function.')
        except Exception:
            raise rest_exception.AuthenticationFailed('token is not valid')
        
        # If authentication is successful, return None (anonymous user) or (user, None).
        return None
