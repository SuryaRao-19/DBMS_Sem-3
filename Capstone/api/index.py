"""
Vercel Serverless Function Entrypoint
Exposes the Flask WSGI application object `app` for Vercel's Python runtime.
"""
import os
import sys
from urllib.parse import parse_qs

# Ensure project root is importable regardless of serverless working directory
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import create_app

app = create_app()


class VercelPathCorrectionMiddleware:
    """
    Restores the original browser request path on Vercel.
    Vercel rewrites incoming requests to /api/index?__path=$1.
    This middleware extracts __path, sets PATH_INFO accordingly, and cleans
    QUERY_STRING so standard Flask routing and query parameters work perfectly.
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        qs = environ.get("QUERY_STRING", "")
        if "__path=" in qs or "__path" in qs:
            params = parse_qs(qs, keep_blank_values=True)
            if "__path" in params and params["__path"]:
                raw_path = params["__path"][0]
                target_path = "/" + raw_path.lstrip("/")
                environ["PATH_INFO"] = target_path
            else:
                environ["PATH_INFO"] = "/"

            cleaned_pairs = [p for p in qs.split("&") if not p.startswith("__path=") and p != "__path"]
            environ["QUERY_STRING"] = "&".join(cleaned_pairs)
        elif environ.get("PATH_INFO") == "/api/index":
            environ["PATH_INFO"] = "/"
        return self.wsgi_app(environ, start_response)


app.wsgi_app = VercelPathCorrectionMiddleware(app.wsgi_app)


