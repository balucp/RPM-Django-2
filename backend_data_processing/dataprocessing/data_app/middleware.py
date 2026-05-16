class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if "/swagger" in request.path in request.path:
            # Looser policy just for Swagger UI
            response["Content-Security-Policy"] = (
                "default-src 'self' https:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval';"
            )
        else:
            # Strict policy for everything else
            response["Content-Security-Policy"] = (
                "default-src 'self' https:;base-uri 'self';block-all-mixed-content;"
                "font-src 'self' https: data:;frame-ancestors 'self';img-src 'self' data:;"
                "object-src 'none';script-src 'self';script-src-attr 'none';style-src 'self';"
                "upgrade-insecure-requests;require-trusted-types-for 'script';"
            )

        response["Access-Control-Allow-Headers"] = "Content-Type"
        response["Access-Control-Allow-Origin"] = "*"
        return response
