"""
Authentication API endpoints — STUB (W3a + W3c).

Single-user fork: every endpoint succeeds and returns the fixed local user
with placeholder "local" tokens. Schemas are inlined here because the original
`schemas/auth_schemas.py`, refresh-token repository, token service, and auth
service modules were removed in W3c.
"""

import structlog
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel

from ..core.local_user import build_local_user
from ..models.user import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/auth", tags=["authentication"])


# ===== Inlined request/response schemas (lenient — accept any payload) =====


class SendCodeRequest(BaseModel):
    auth_type: str | None = None
    identifier: str = ""

    model_config = {"extra": "allow"}


class SendCodeResponse(BaseModel):
    message: str
    code: str | None = None


class VerifyCodeRequest(BaseModel):
    model_config = {"extra": "allow"}


class RegisterRequest(BaseModel):
    model_config = {"extra": "allow"}


class LoginRequest(BaseModel):
    model_config = {"extra": "allow"}


class ResetPasswordRequest(BaseModel):
    model_config = {"extra": "allow"}


class RefreshTokenRequest(BaseModel):
    refresh_token: str | None = None

    model_config = {"extra": "allow"}


class LogoutRequest(BaseModel):
    refresh_token: str | None = None

    model_config = {"extra": "allow"}


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    refresh_expires_in: int


class LoginResponse(TokenPair):
    user: User


# ===== Stub endpoints =====

_FAKE_TOKEN = "local"  # noqa: S105 — intentional placeholder for stubbed auth
_FAKE_EXPIRES_IN = 60 * 60 * 24 * 365  # 1 year
_FAKE_REFRESH_EXPIRES_IN = 60 * 60 * 24 * 365  # 1 year


def _login_response() -> LoginResponse:
    return LoginResponse(
        access_token=_FAKE_TOKEN,
        refresh_token=_FAKE_TOKEN,
        token_type="bearer",
        expires_in=_FAKE_EXPIRES_IN,
        refresh_expires_in=_FAKE_REFRESH_EXPIRES_IN,
        user=build_local_user(),
    )


@router.post("/send-code", response_model=SendCodeResponse)
async def send_verification_code(request: SendCodeRequest) -> SendCodeResponse:
    return SendCodeResponse(
        message=f"(stub) Verification code accepted for {request.identifier}",
        code=None,
    )


@router.post("/verify-code", response_model=LoginResponse)
async def verify_code_and_login(
    verify_request: VerifyCodeRequest,
    http_request: Request,
) -> LoginResponse:
    return _login_response()


@router.post("/register", response_model=LoginResponse)
async def register_user(
    register_request: RegisterRequest,
    http_request: Request,
) -> LoginResponse:
    return _login_response()


@router.post("/login", response_model=LoginResponse)
async def login_with_password(
    login_request: LoginRequest,
    http_request: Request,
) -> LoginResponse:
    return _login_response()


@router.post("/reset-password", response_model=LoginResponse)
async def reset_password(
    reset_request: ResetPasswordRequest,
    http_request: Request,
) -> LoginResponse:
    return _login_response()


@router.get("/me", response_model=User)
async def get_current_user_endpoint(
    authorization: str | None = Header(None),
) -> User:
    return build_local_user()


@router.post("/refresh", response_model=TokenPair)
async def refresh_access_token(request: RefreshTokenRequest) -> TokenPair:
    return TokenPair(
        access_token=_FAKE_TOKEN,
        refresh_token=_FAKE_TOKEN,
        token_type="bearer",
        expires_in=_FAKE_EXPIRES_IN,
        refresh_expires_in=_FAKE_REFRESH_EXPIRES_IN,
    )


@router.post("/logout")
async def logout(request: LogoutRequest) -> dict[str, str]:
    return {"message": "Logged out successfully"}


@router.post("/logout-all")
async def logout_all_devices(
    authorization: str | None = Header(None),
) -> dict[str, str]:
    return {"message": "Logged out from all devices (0 tokens revoked)"}
