"""BhuSanket API entry point."""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

from .auth import current_user, require_roles
from .ml_model import compare_risk


app = FastAPI(title="BhuSanket API", version="0.1.0")
origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:8000").split(",") if origin.strip()]
app.add_middleware(
	CORSMiddleware,
	allow_origins=origins,
	allow_credentials=True,
	allow_methods=["GET", "POST", "PATCH"],
	allow_headers=["Authorization", "Content-Type"],
)


class ZoneInputs(BaseModel):
	rainfall: float = Field(ge=0)
	accumulated: float = Field(ge=0)
	moisture: float = Field(ge=0, le=100)
	slope: float = Field(ge=0, le=100)
	susceptibility: float = Field(ge=0, le=100)
	history: float = Field(ge=0, le=100)
	exposure: float = Field(ge=0, le=100)


@app.get("/api/health")
def health() -> dict[str, str]:
	return {"status": "ok", "service": "BhuSanket API"}


@app.get("/api/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
	return {
		"id": user.get("sub"),
		"email": user.get("email"),
		"role": (user.get("app_metadata") or {}).get("role", "Citizen"),
	}


@app.get("/api/admin/users")
def admin_users(user: dict[str, Any] = Depends(require_roles("Admin"))) -> dict[str, Any]:
	return {"message": "Admin route ready for user-management integration", "requested_by": user.get("sub")}


@app.post("/api/reports")
def create_report(user: dict[str, Any] = Depends(require_roles("Admin", "District official", "Field officer", "Citizen"))) -> dict[str, Any]:
	return {"message": "Report route ready for database integration", "submitted_by": user.get("sub")}


@app.post("/api/ml/compare")
def ml_compare(zone: ZoneInputs, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
	return compare_risk(zone.model_dump())
