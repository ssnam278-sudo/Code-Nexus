"""Supabase JWT verification and role-based access dependencies."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


bearer = HTTPBearer(auto_error=False)


def _settings() -> tuple[str, str]:
	url = os.getenv("SUPABASE_URL", "").rstrip("/")
	audience = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")
	if not url:
		raise HTTPException(status_code=503, detail="Authentication is not configured")
	return url, audience


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
	url, _ = _settings()
	return jwt.PyJWKClient(f"{url}/auth/v1/.well-known/jwks.json")


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict[str, Any]:
	if credentials is None or credentials.scheme.lower() != "bearer":
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
	url, audience = _settings()
	try:
		signing_key = _jwks_client().get_signing_key_from_jwt(credentials.credentials)
		return jwt.decode(
			credentials.credentials,
			signing_key.key,
			audience=audience,
			issuer=f"{url}/auth/v1",
			algorithms=["ES256", "RS256"],
		)
	except (jwt.PyJWTError, ValueError) as error:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from error


def require_roles(*allowed_roles: str) -> Callable[..., dict[str, Any]]:
	def dependency(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
		metadata = user.get("app_metadata") or {}
		role = metadata.get("role", "Citizen")
		if role not in allowed_roles:
			raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
		return user

	return dependency
