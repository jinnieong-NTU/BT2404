"""Server-side faculty authorization module.

Enforces privileged access to faculty settings and controls.
"""

from typing import Optional
from fastapi import Header, HTTPException, status, Depends
from app.config import settings


def get_faculty_token_from_headers(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_faculty_token: Optional[str] = Header(None, alias="X-Faculty-Token"),
) -> Optional[str]:
    """Extract token from Authorization (Bearer) or X-Faculty-Token header."""
    if x_faculty_token:
        return x_faculty_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def verify_faculty_token(token: Optional[str]) -> bool:
    """Validate token against configured faculty secret."""
    if not token or not settings.FACULTY_SECRET_TOKEN:
        return False
    # Constant-time comparison
    import hmac

    return hmac.compare_digest(token, settings.FACULTY_SECRET_TOKEN)


def require_faculty_admin(
    token: Optional[str] = Depends(get_faculty_token_from_headers),
) -> bool:
    """FastAPI dependency for faculty-only routes.

    Raises 401 Unauthorized if invalid or missing token.
    """
    if not verify_faculty_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Faculty authorization required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True


def optional_faculty_admin(
    token: Optional[str] = Depends(get_faculty_token_from_headers),
) -> bool:
    """Returns True if the request is from an authenticated faculty admin, False otherwise.

    Does not throw exceptions.
    """
    return verify_faculty_token(token)
