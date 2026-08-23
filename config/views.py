"""Serve challenge static files and homepage redirect."""
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.views.static import serve


CHALLENGE_DIR = Path(settings.BASE_DIR) / "challenge"


def home(request):
    """Serve the mission grid homepage."""
    index = CHALLENGE_DIR / "index.html"
    if not index.exists():
        raise Http404("index.html not found")
    return FileResponse(open(index, "rb"), content_type="text/html")


def challenge_file(request, path):
    """Serve any file from the challenge/ directory."""
    full = (CHALLENGE_DIR / path).resolve()
    if not str(full).startswith(str(CHALLENGE_DIR.resolve())):
        raise Http404()
    if not full.is_file():
        raise Http404()
    return serve(request, path, document_root=str(CHALLENGE_DIR))
