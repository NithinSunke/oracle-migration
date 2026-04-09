from fastapi import APIRouter, HTTPException, status

from backend.app.schemas.auth import AuthSessionResponse, UserLoginRequest, UserRegisterRequest
from backend.app.services.auth_service import (
    AuthConflictError,
    AuthCredentialsError,
    auth_service,
)

router = APIRouter()


@router.post(
    "/register",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(request: UserRegisterRequest) -> AuthSessionResponse:
    try:
        return auth_service.register(request)
    except AuthConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


@router.post("/login", response_model=AuthSessionResponse)
async def login_user(request: UserLoginRequest) -> AuthSessionResponse:
    try:
        return auth_service.login(request)
    except AuthCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
        ) from error
