from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone

from sqlalchemy import select

from backend.app.core.database import session_scope
from backend.app.models.persistence import AppUserModel
from backend.app.schemas.auth import AuthSessionResponse, UserLoginRequest, UserRegisterRequest


class AuthConflictError(ValueError):
    pass


class AuthCredentialsError(ValueError):
    pass


class AuthService:
    _iterations = 120_000

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _generate_salt() -> str:
        return os.urandom(16).hex()

    def _hash_password(self, password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            self._iterations,
        ).hex()

    def register(self, request: UserRegisterRequest) -> AuthSessionResponse:
        with session_scope() as session:
            existing = session.execute(
                select(AppUserModel).where(AppUserModel.username == request.username)
            ).scalar_one_or_none()
            if existing is not None:
                raise AuthConflictError(
                    f"Username '{request.username}' is already registered."
                )

            password_salt = self._generate_salt()
            user = AppUserModel(
                username=request.username,
                password_salt=password_salt,
                password_hash=self._hash_password(request.password, password_salt),
            )
            session.add(user)
            session.flush()

            authenticated_at = self._utcnow()
            return AuthSessionResponse(
                user_id=user.user_id,
                username=user.username,
                authenticated_at=authenticated_at,
                persistent=request.persistent,
            )

    def login(self, request: UserLoginRequest) -> AuthSessionResponse:
        with session_scope() as session:
            user = session.execute(
                select(AppUserModel).where(AppUserModel.username == request.username)
            ).scalar_one_or_none()
            if user is None or not user.is_active:
                raise AuthCredentialsError("Invalid username or password.")

            computed_hash = self._hash_password(request.password, user.password_salt)
            if not hmac.compare_digest(computed_hash, user.password_hash):
                raise AuthCredentialsError("Invalid username or password.")

            authenticated_at = self._utcnow()
            return AuthSessionResponse(
                user_id=user.user_id,
                username=user.username,
                authenticated_at=authenticated_at,
                persistent=request.persistent,
            )


auth_service = AuthService()
