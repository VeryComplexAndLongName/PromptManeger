import os
import time
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from loguru import logger
from sqlalchemy.orm import Session

import crud
from database import SessionLocal
from models import Config, Role, User
from optimizer_service import build_optimizer_config, get_runtime_optimizer_config
from security import (
    ACCESS_TOKEN_TTL_SECONDS,
    REFRESH_TOKEN_TTL_SECONDS,
    create_access_token,
    create_refresh_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    verify_access_token,
    verify_password,
    verify_refresh_token,
)

_DEFAULT_BOOTSTRAP_ADMIN_USERNAME = "admin"
_DEFAULT_BOOTSTRAP_ADMIN_PASSWORD = "admin"
_DEFAULT_ROLE_NAMES = ("admin", "developer", "viewer")


def _normalize_role(value: str | None, db: Session) -> str:
    role = (value or "developer").strip().lower()
    if not crud.get_role_by_name(db, role):
        raise HTTPException(status_code=400, detail="Invalid role")
    return role


def get_db_session():  # type: ignore[no-untyped-def]
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def issue_tokens_for_user(user: User) -> dict[str, Any]:
    issued_at = int(time.time())
    return {
        "access_token": create_access_token(
            user_id=user.id,
            username=user.username,
            role=user.role,
            ttl_seconds=ACCESS_TOKEN_TTL_SECONDS,
            now_ts=issued_at,
        ),
        "refresh_token": create_refresh_token(
            user_id=user.id,
            username=user.username,
            role=user.role,
            ttl_seconds=REFRESH_TOKEN_TTL_SECONDS,
            now_ts=issued_at,
        ),
        "token_type": "bearer",
        "access_token_ttl_seconds": ACCESS_TOKEN_TTL_SECONDS,
        "refresh_token_ttl_seconds": REFRESH_TOKEN_TTL_SECONDS,
        "access_token_expires_at": issued_at + ACCESS_TOKEN_TTL_SECONDS,
        "refresh_token_expires_at": issued_at + REFRESH_TOKEN_TTL_SECONDS,
    }


def build_auth_response(user: User) -> dict[str, Any]:
    return {
        **issue_tokens_for_user(user),
        "user": user_to_dict(user),
    }


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = crud.get_user_by_username(db, username)
    if not user or not user.is_active:
        return None
    stored_hash = decrypt_secret(user.password_hash_encrypted)
    if not verify_password(password, stored_hash):
        return None
    return user


def user_to_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "projects": [item.project for item in user.project_access],
    }


def create_user_record(
    db: Session,
    *,
    username: str,
    password: str,
    role: str,
    is_active: bool = True,
    projects: list[str] | None = None,
) -> User:
    normalized_role = _normalize_role(role, db)
    if crud.get_user_by_username(db, username):
        raise HTTPException(status_code=409, detail="Username already exists")
    password_hash_encrypted = encrypt_secret(hash_password(password))
    if not password_hash_encrypted:
        raise HTTPException(status_code=500, detail="Unable to encrypt password hash")
    return crud.create_user(
        db,
        username=username,
        password_hash_encrypted=password_hash_encrypted,
        role=normalized_role,
        is_active=is_active,
        projects=projects,
    )


def update_user_record(
    db: Session,
    user: User,
    *,
    username: str | None = None,
    password: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    projects: list[str] | None = None,
) -> User:
    encrypted_hash: str | None = None
    if username is not None:
        existing = crud.get_user_by_username(db, username)
        if existing and existing.id != user.id:
            raise HTTPException(status_code=409, detail="Username already exists")
    if password is not None:
        encrypted_hash = encrypt_secret(hash_password(password))
        if not encrypted_hash:
            raise HTTPException(status_code=500, detail="Unable to encrypt password hash")
    normalized_role = _normalize_role(role, db) if role is not None else None
    return crud.update_user(
        db,
        user,
        username=username,
        password_hash_encrypted=encrypted_hash,
        role=normalized_role,
        is_active=is_active,
        projects=projects,
    )


def _extract_bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:].strip()
    return token or None


def get_current_user(request: Request, db: Session = Depends(get_db_session)) -> User:
    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = crud.get_user_by_id(db, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")
    return user


def refresh_session(db: Session, refresh_token: str) -> dict[str, Any]:
    payload = verify_refresh_token(refresh_token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = crud.get_user_by_id(db, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")

    return build_auth_response(user)


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user


def require_write_access(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role == "viewer":
        raise HTTPException(status_code=403, detail="Viewer role is read-only")
    return current_user


def allowed_projects_for_user(user: User) -> list[str] | None:
    if user.role == "admin" or user.role == "viewer":
        return None
    return [item.project for item in user.project_access]


def ensure_project_access(user: User, project: str) -> None:
    allowed_projects = allowed_projects_for_user(user)
    if allowed_projects is None:
        return
    if project not in allowed_projects:
        raise HTTPException(status_code=404, detail="Prompt not found")


def serialize_optimizer_config(config: Config | None) -> dict[str, Any]:
    if config is None:
        return get_runtime_optimizer_config()

    if all(
        value is None
        for value in (
            config.llm_provider,
            config.llm_model,
            config.llm_base_url,
            config.llm_timeout_seconds,
            config.llm_api_token_encrypted,
        )
    ):
        return get_runtime_optimizer_config()

    overrides = {
        "llm_provider": config.llm_provider,
        "llm_model": config.llm_model,
        "llm_base_url": config.llm_base_url,
        "llm_timeout_seconds": config.llm_timeout_seconds,
        "llm_api_token": decrypt_secret(config.llm_api_token_encrypted),
    }
    result = build_optimizer_config(overrides)
    result["runtime_has_llm_api_token"] = bool(config and config.llm_api_token_encrypted)
    return result


def get_or_create_personal_config(db: Session, user: User) -> Config:
    return crud.get_or_create_user_config(db, user.id)


def update_personal_config(db: Session, user: User, payload: dict[str, Any]) -> dict[str, Any]:
    config = get_or_create_personal_config(db, user)
    if "llm_provider" in payload and payload.get("llm_provider") is not None:
        config.llm_provider = str(payload["llm_provider"]).strip().lower() or "ollama"
    if "llm_model" in payload and payload.get("llm_model") is not None:
        config.llm_model = str(payload["llm_model"]).strip() or "qwen2.5:0.5b"
    if "llm_base_url" in payload and payload.get("llm_base_url") is not None:
        config.llm_base_url = str(payload["llm_base_url"]).strip() or "http://127.0.0.1:11434"
    if "llm_timeout_seconds" in payload and payload.get("llm_timeout_seconds") is not None:
        config.llm_timeout_seconds = max(5, int(payload["llm_timeout_seconds"]))
    if "llm_api_token" in payload:
        config.llm_api_token_encrypted = encrypt_secret(payload.get("llm_api_token"))
    db.add(config)
    db.commit()
    db.refresh(config)
    return serialize_optimizer_config(config)


def maybe_bootstrap_admin(db: Session) -> None:
    crud.ensure_default_roles(db)
    if crud.list_users(db):
        return
    username = (os.getenv("BOOTSTRAP_ADMIN_USERNAME") or _DEFAULT_BOOTSTRAP_ADMIN_USERNAME).strip()
    password = (os.getenv("BOOTSTRAP_ADMIN_PASSWORD") or _DEFAULT_BOOTSTRAP_ADMIN_PASSWORD).strip()
    logger.warning("auth.bootstrap.default_admin_created username={}", username)
    create_user_record(db, username=username, password=password, role="admin", is_active=True, projects=[])


def list_roles_out(db: Session) -> list[dict[str, Any]]:
    crud.ensure_default_roles(db)
    return [{"id": role.id, "name": role.name} for role in crud.list_roles(db)]
