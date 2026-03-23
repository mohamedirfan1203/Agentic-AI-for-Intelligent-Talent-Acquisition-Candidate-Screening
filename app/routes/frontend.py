"""
Frontend Routes
===============
Serves the frontend static files (HTML, CSS, JS) from the /frontend directory.
"""

import os
from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["Frontend"])

FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend",
)


@router.get("/portal", summary="HR-Bot Portal (Frontend)")
async def serve_portal():
    """Serves the main portal HTML page."""
    return FileResponse(
        os.path.join(FRONTEND_DIR, "index.html"),
        media_type="text/html",
    )


@router.get("/portal/{filename}", summary="Frontend static files")
async def serve_static(filename: str):
    """Serves CSS, JS, and other static frontend assets."""
    file_path = os.path.join(FRONTEND_DIR, filename)
    if not os.path.exists(file_path):
        return FileResponse(
            os.path.join(FRONTEND_DIR, "index.html"),
            media_type="text/html",
        )

    # Determine media type
    ext = filename.rsplit(".", 1)[-1].lower()
    media_types = {
        "css": "text/css",
        "js": "application/javascript",
        "html": "text/html",
        "png": "image/png",
        "jpg": "image/jpeg",
        "svg": "image/svg+xml",
        "ico": "image/x-icon",
    }
    return FileResponse(file_path, media_type=media_types.get(ext, "application/octet-stream"))
