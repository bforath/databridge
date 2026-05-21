from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.openapi.models import Example
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.container import get_auth_service
from schemas.user import LoginRequest, TokenResponse
from services.auth_service import AuthService
from services.exceptions import AccountDisabledError, AuthenticationError

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

_LOGIN_EXAMPLES: dict[str, Example] = {
    "admin": Example(summary="Admin — full access", value={"email": "admin@databridge.io", "password": "admin"}),
    "viewer": Example(summary="Viewer — read-only", value={"email": "demo@databridge.io", "password": "demo"}),
}


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(
    request: Request,
    body: LoginRequest = Body(openapi_examples=_LOGIN_EXAMPLES),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    try:
        token = service.authenticate(body.email, body.password)
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    except AccountDisabledError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    return TokenResponse(access_token=token)
