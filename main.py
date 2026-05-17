import datetime
import importlib.metadata
import logging
import os
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path
from time import perf_counter
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

import auth_service
import crud
from database import SessionLocal, init_database
from models import Prompt, User
from optimizer_service import (
    build_optimizer_config,
    list_available_llm_models,
    optimize_with_greaterprompt,
    optimize_with_llm,
)
from schemas import (
    AuthResponse,
    AuthStatus,
    OptimizeConfigOut,
    OptimizeConfigUpdate,
    ProjectCreate,
    ProjectOut,
    RoleOut,
    PromptCreate,
    PromptData,
    PromptOptimizeResponse,
    PromptOut,
    PromptVersionOut,
    PromptTagsUpdate,
    PromptUpdate,
    ProjectAccessUpdate,
    ProjectUpdate,
    RefreshTokenRequest,
    UserBootstrap,
    UserCreate,
    UserLogin,
    UserOut,
    UserUpdate,
)


def _resolve_app_version() -> str:
    try:
        return importlib.metadata.version("prompt-man")
    except importlib.metadata.PackageNotFoundError:
        pass

    pyproject_path = Path(__file__).resolve().parent / "pyproject.toml"
    if pyproject_path.exists():
        try:
            with pyproject_path.open("rb") as fp:
                pyproject = tomllib.load(fp)
            version = pyproject.get("project", {}).get("version")
            if isinstance(version, str) and version.strip():
                return version.strip()
        except Exception:
            pass

    return "0.0.0"


APP_VERSION = _resolve_app_version()


app = FastAPI(title="Prompt Man", version=APP_VERSION)
app.mount("/ui", StaticFiles(directory="ui"), name="ui")

CONSOLE_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
SHOW_CONSOLE_SOURCE = os.getenv("SHOW_CONSOLE_SOURCE", "0").strip().lower() in {"1", "true", "yes", "on"}


def _console_log_format(record: dict) -> str:
    def _escape_markup(value: object) -> str:
        return str(value).replace("<", "\\<").replace(">", "\\>")

    message = _escape_markup(record["message"])
    source = f"{_escape_markup(record['name'])}:{_escape_markup(record['function'])}:{record['line']}"
    badge = "<white>APP     </white>"
    message_color = "<level>"

    if message.startswith("request.start"):
        badge = "<blue>HTTP IN </blue>"
        message_color = "<blue>"
    elif message.startswith("request.end"):
        badge = "<green>HTTP OUT</green>"
        message_color = "<green>"
    elif message.startswith("request.error") or message.startswith("request.exception"):
        badge = "<red>HTTP ERR</red>"
        message_color = "<red>"
    elif message.startswith("optimize.greaterprompt") or message.startswith("optimize.gradient"):
        badge = "<magenta>GP      </magenta>"
        message_color = "<magenta>"
    elif message.startswith("optimize.llm"):
        badge = "<yellow>LLM     </yellow>"
        message_color = "<yellow>"
    elif message.startswith("optimize.config"):
        badge = "<cyan>CFG     </cyan>"
        message_color = "<cyan>"
    elif message.startswith("logging.configured"):
        badge = "<green>BOOT    </green>"
        message_color = "<green>"

    source_part = f" <cyan>{source}</cyan> " if SHOW_CONSOLE_SOURCE else ""

    return (
        f"<dim>{record['time'].astimezone(datetime.timezone.utc):YYYY-MM-DD HH:mm:ss.SSS} UTC</dim> "
        f"{badge} "
        f"<level>{record['level'].name:<8}</level> "
        f"{source_part}"
        f"{message_color}{message}</>\n{{exception}}"
    )


def configure_logging() -> None:
    os.makedirs("logs", exist_ok=True)
    logger.remove()
    logger.add(
        sys.stderr,
        level=CONSOLE_LOG_LEVEL,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        colorize=True,
        format=_console_log_format,
    )
    logger.add(
        "logs/app.log",
        level="DEBUG",
        rotation="10 MB",
        retention="10 days",
        enqueue=True,
        backtrace=True,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS!UTC} UTC | {level} | {name}:{function}:{line} | {message}",
    )

    # Uvicorn access logs have their own formatter and make console output inconsistent
    # with the application logs emitted through Loguru below.
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.handlers.clear()
    uvicorn_access_logger.propagate = False

    uvicorn_error_logger = logging.getLogger("uvicorn.error")
    uvicorn_error_logger.handlers.clear()
    uvicorn_error_logger.propagate = False


class ExceptionLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        started_at = perf_counter()
        try:
            return await call_next(request)
        except Exception:
            duration_ms = (perf_counter() - started_at) * 1000
            client = request.client.host if request.client else "unknown"
            logger.exception(
                "request.exception method={} path={} query={} client={} duration_ms={:.2f}",
                request.method,
                request.url.path,
                request.url.query,
                client,
                duration_ms,
            )
            return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        start = perf_counter()
        client = request.client.host if request.client else "unknown"
        logger.info(
            "request.start method={} path={} query={} client={}",
            request.method,
            request.url.path,
            request.url.query,
            client,
        )

        response = await call_next(request)

        duration_ms = (perf_counter() - start) * 1000
        logger.info(
            "request.end method={} path={} status={} duration_ms={:.2f}",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


configure_logging()
logger.info("logging.configured sinks=console+file")

# Order matters: request logging stays outermost so every request is traced,
# while exception middleware centralizes uncaught exceptions and returns a
# consistent 500 response.
app.add_middleware(ExceptionLoggingMiddleware)
app.add_middleware(RequestLoggingMiddleware)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def bootstrap_admin_if_needed() -> None:
    init_database()
    db = SessionLocal()
    try:
        auth_service.maybe_bootstrap_admin(db)
    finally:
        db.close()


def to_user_out(user: User) -> UserOut:
    return UserOut(**auth_service.user_to_dict(user))


def to_project_out(project) -> ProjectOut:  # type: ignore[no-untyped-def]
    return ProjectOut(id=project.id, name=project.name)


def get_personal_config(db: Session, current_user: User) -> dict:
    config = auth_service.get_or_create_personal_config(db, current_user)
    return auth_service.serialize_optimizer_config(config)


def allowed_projects(current_user: User) -> list[str] | None:
    return auth_service.allowed_projects_for_user(current_user)


def normalize_utc_datetime(value: datetime.datetime | None) -> datetime.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def to_prompt_out(db: Session, prompt: Prompt) -> PromptOut:
    latest = crud.get_latest_version(db, prompt.id)
    if not latest:
        raise ValueError(f"No version found for prompt {prompt.id}")
    return PromptOut(
        name=prompt.name,
        project=prompt.project,
        created_at=normalize_utc_datetime(prompt.created_at),
        updated_at=normalize_utc_datetime(prompt.updated_at),
        created_by_username=crud.resolve_audit_username(db, prompt.created_by_ref),
        updated_by_username=crud.resolve_audit_username(db, prompt.updated_by_ref),
        tags=[tag.name for tag in prompt.tags],
        latest_version=latest.version,
        role=latest.role,
        task=latest.task,
        context=latest.context,
        constraints=latest.constraints,
        output_format=latest.output_format,
        examples=latest.examples,
    )


def to_prompt_version_out(db: Session, version) -> PromptVersionOut:  # type: ignore[no-untyped-def]
    return PromptVersionOut(
        version=version.version,
        created_at=normalize_utc_datetime(version.created_at),
        created_by_username=crud.resolve_audit_username(db, version.created_by_ref),
        role=version.role,
        task=version.task,
        context=version.context,
        constraints=version.constraints,
        output_format=version.output_format,
        examples=version.examples,
    )


@app.get("/", include_in_schema=False)
def serve_ui() -> FileResponse:
    return FileResponse("ui/html/index.html")


@app.post("/auth/bootstrap-admin", response_model=AuthResponse)
def bootstrap_admin(data: UserBootstrap, db: Session = Depends(get_db)) -> AuthResponse:
    if crud.list_users(db):
        raise HTTPException(409, "Users already exist")
    user = auth_service.create_user_record(
        db,
        username=data.username,
        password=data.password,
        role="admin",
        is_active=True,
        projects=[],
    )
    return AuthResponse(**auth_service.build_auth_response(user))


@app.post("/auth/login", response_model=AuthResponse)
def login(data: UserLogin, db: Session = Depends(get_db)) -> AuthResponse:
    user = auth_service.authenticate_user(db, data.username, data.password)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    return AuthResponse(**auth_service.build_auth_response(user))


@app.post("/auth/refresh", response_model=AuthResponse)
def refresh_auth(data: RefreshTokenRequest, db: Session = Depends(get_db)) -> AuthResponse:
    return AuthResponse(**auth_service.refresh_session(db, data.refresh_token))


@app.get("/auth/status", response_model=AuthStatus)
def get_auth_status(db: Session = Depends(get_db)) -> AuthStatus:
    has_users = bool(crud.list_users(db))
    return AuthStatus(bootstrap_required=not has_users, has_users=has_users)


@app.get("/version")
def get_version() -> dict[str, str]:
    return {"name": "prompt-man", "version": APP_VERSION}


@app.get("/auth/me", response_model=UserOut)
def get_me(current_user: User = Depends(auth_service.get_current_user)) -> UserOut:
    return to_user_out(current_user)


@app.get("/roles", response_model=list[RoleOut])
def list_roles(db: Session = Depends(get_db), _: User = Depends(auth_service.require_admin)) -> list[RoleOut]:
    return [RoleOut(**item) for item in auth_service.list_roles_out(db)]


@app.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(auth_service.require_admin)) -> list[UserOut]:
    return [to_user_out(user) for user in crud.list_users(db)]


@app.post("/users", response_model=UserOut)
def create_user(data: UserCreate, db: Session = Depends(get_db), _: User = Depends(auth_service.require_admin)) -> UserOut:
    user = auth_service.create_user_record(
        db,
        username=data.username,
        password=data.password,
        role=data.role,
        is_active=data.is_active,
        projects=data.projects,
    )
    return to_user_out(user)


@app.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(auth_service.require_admin)) -> UserOut:
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return to_user_out(user)


@app.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db), current_admin: User = Depends(auth_service.require_admin)) -> UserOut:
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if current_admin.id == user.id and data.role is not None and data.role != "admin":
        raise HTTPException(400, "Admin cannot remove own admin role")
    updated = auth_service.update_user_record(
        db,
        user,
        username=data.username,
        password=data.password,
        role=data.role,
        is_active=data.is_active,
        projects=data.projects,
    )
    return to_user_out(updated)


@app.put("/users/{user_id}/projects", response_model=UserOut)
def update_user_projects(user_id: int, data: ProjectAccessUpdate, db: Session = Depends(get_db), _: User = Depends(auth_service.require_admin)) -> UserOut:
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    updated = crud.set_user_projects(db, user, data.projects)
    return to_user_out(updated)


@app.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db), current_admin: User = Depends(auth_service.require_admin)) -> Response:
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if current_admin.id == user.id:
        raise HTTPException(400, "Admin cannot delete self")
    crud.delete_user(db, user)
    return Response(status_code=204)


@app.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), _: User = Depends(auth_service.require_admin)) -> list[ProjectOut]:
    return [to_project_out(project) for project in crud.list_projects(db)]


@app.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db), _: User = Depends(auth_service.require_admin)) -> ProjectOut:
    project = crud.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return to_project_out(project)


@app.post("/projects", response_model=ProjectOut)
def create_project(data: ProjectCreate, db: Session = Depends(get_db), _: User = Depends(auth_service.require_admin)) -> ProjectOut:
    try:
        project = crud.create_project(db, data.name)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return to_project_out(project)


@app.put("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, data: ProjectUpdate, db: Session = Depends(get_db), _: User = Depends(auth_service.require_admin)) -> ProjectOut:
    project = crud.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    try:
        updated = crud.update_project(db, project, name=data.name)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return to_project_out(updated)


@app.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db), _: User = Depends(auth_service.require_admin)) -> Response:
    project = crud.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    crud.delete_project(db, project)
    return Response(status_code=204)


@app.get("/prompts/search", response_model=list[PromptOut])
def search_prompts(
    tags: list[str] = Query(..., description="Tags to filter by (repeat for multiple)"),
    mode: Literal["and", "or"] = Query("or", description="'and' requires all tags; 'or' requires any tag"),
    project: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[PromptOut]:
    if project is not None:
        auth_service.ensure_project_access(current_user, project)
    prompts = crud.search_prompts_by_tags(db, tags=tags, mode=mode, project=project, allowed_projects=allowed_projects(current_user))
    return [to_prompt_out(db, p) for p in prompts]


@app.get("/prompts", response_model=list[PromptOut])
def list_prompts(
    response: Response,
    project: str | None = None,
    tag: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[PromptOut]:
    # Convert string parameters to int safely
    limit_int: int | None = None
    offset_int: int | None = None
    try:
        if limit:
            limit_int = int(limit)
            if limit_int < 1:
                limit_int = 1
    except (ValueError, TypeError):
        limit_int = None
    
    try:
        if offset:
            offset_int = int(offset)
            if offset_int < 0:
                offset_int = 0
    except (ValueError, TypeError):
        offset_int = None
    
    if project is not None:
        auth_service.ensure_project_access(current_user, project)
    total_count = crud.count_prompts(db, project=project, tag=tag, allowed_projects=allowed_projects(current_user))
    response.headers["X-Total-Count"] = str(total_count)
    prompts = crud.list_prompts(db, project=project, tag=tag, limit=limit_int, offset=offset_int, allowed_projects=allowed_projects(current_user))
    return [to_prompt_out(db, prompt) for prompt in prompts]


@app.post("/prompts", response_model=PromptOut)
def create_prompt(data: PromptCreate, db: Session = Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> PromptOut:
    logger.info("prompt.create name={} project={}", data.name, data.project)
    auth_service.ensure_project_access(current_user, data.project)
    prompt = crud.get_prompt(db, data.name, data.project, allowed_projects=allowed_projects(current_user))
    if prompt:
        logger.warning("prompt.create.duplicate name={} project={}", data.name, data.project)
        raise HTTPException(400, "Prompt already exists")

    try:
        prompt = crud.create_prompt(
            db,
            data.name,
            data.project,
            task=data.task,
            actor_id=current_user.id,
            role=data.role,
            context=data.context,
            constraints=data.constraints,
            output_format=data.output_format,
            examples=data.examples,
            tags=data.tags,
        )
    except ValueError as exc:
        logger.warning("prompt.create.duplicate_content name={} project={}", data.name, data.project)
        raise HTTPException(409, str(exc)) from exc
    return to_prompt_out(db, prompt)


@app.get("/prompts/{project}/{name}", response_model=PromptOut)
def get_prompt(project: str, name: str, db: Session = Depends(get_db), current_user: User = Depends(auth_service.get_current_user)) -> PromptOut:
    auth_service.ensure_project_access(current_user, project)
    prompt = crud.get_prompt(db, name, project, allowed_projects=allowed_projects(current_user))
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    return to_prompt_out(db, prompt)


@app.delete("/prompts/{project}/{name}", status_code=204)
def delete_prompt(project: str, name: str, db: Session = Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> Response:
    logger.info("prompt.delete project={} name={}", project, name)
    auth_service.ensure_project_access(current_user, project)
    prompt = crud.get_prompt(db, name, project, allowed_projects=allowed_projects(current_user))
    if not prompt:
        logger.warning("prompt.delete.not_found project={} name={}", project, name)
        raise HTTPException(404, "Prompt not found")

    crud.delete_prompt(db, prompt)
    return Response(status_code=204)


@app.put("/prompts/{project}/{name}", response_model=PromptVersionOut)
def update_prompt(project: str, name: str, data: PromptUpdate, db: Session = Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> PromptVersionOut:
    logger.info("prompt.update project={} name={}", project, name)
    auth_service.ensure_project_access(current_user, project)
    prompt = crud.get_prompt(db, name, project, allowed_projects=allowed_projects(current_user))
    if not prompt:
        logger.warning("prompt.update.not_found project={} name={}", project, name)
        raise HTTPException(404, "Prompt not found")

    if data.tags is not None:
        crud.set_prompt_tags(db, prompt, data.tags, actor_id=current_user.id)

    try:
        new_version = crud.add_version(
            db,
            prompt.id,
            task=data.task,
            actor_id=current_user.id,
            role=data.role,
            context=data.context,
            constraints=data.constraints,
            output_format=data.output_format,
            examples=data.examples,
        )
    except ValueError as exc:
        logger.warning("prompt.update.conflict project={} name={} error={}", project, name, str(exc))
        raise HTTPException(409, str(exc)) from exc
    return to_prompt_version_out(db, new_version)


@app.put("/prompts/{project}/{name}/tags", response_model=PromptOut)
def update_prompt_tags(project: str, name: str, data: PromptTagsUpdate, db: Session = Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> PromptOut:
    auth_service.ensure_project_access(current_user, project)
    prompt = crud.get_prompt(db, name, project, allowed_projects=allowed_projects(current_user))
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    crud.set_prompt_tags(db, prompt, data.tags, actor_id=current_user.id)
    # Reload prompt from database to ensure all relationships are properly populated
    prompt = crud.get_prompt(db, name, project, allowed_projects=allowed_projects(current_user))
    if not prompt:
        raise HTTPException(404, "Prompt not found after update")
    return to_prompt_out(db, prompt)


@app.get("/prompts/{project}/{name}/versions", response_model=list[PromptVersionOut])
def list_versions(project: str, name: str, db: Session = Depends(get_db), current_user: User = Depends(auth_service.get_current_user)) -> list[PromptVersionOut]:
    auth_service.ensure_project_access(current_user, project)
    prompt = crud.get_prompt(db, name, project, allowed_projects=allowed_projects(current_user))
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    versions = crud.list_versions(db, prompt.id)
    return [to_prompt_version_out(db, v) for v in versions]


@app.get("/prompts/{project}/{name}/versions/{version}", response_model=PromptVersionOut)
def get_version(project: str, name: str, version: int, db: Session = Depends(get_db), current_user: User = Depends(auth_service.get_current_user)) -> PromptVersionOut:
    auth_service.ensure_project_access(current_user, project)
    prompt = crud.get_prompt(db, name, project, allowed_projects=allowed_projects(current_user))
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    v = crud.get_specific_version(db, prompt.id, version)
    if not v:
        raise HTTPException(404, "Version not found")

    return to_prompt_version_out(db, v)


@app.post("/optimize/greaterprompt", response_model=PromptOptimizeResponse)
def optimize_prompt(data: PromptData, db: Session = Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> PromptOptimizeResponse:
    logger.info("optimize.greaterprompt.start")
    result = optimize_with_greaterprompt(data.model_dump(), get_personal_config(db, current_user))
    logger.info("optimize.greaterprompt.done engine={}", result.engine)
    optimized_dict = result.optimized_fields
    if not isinstance(optimized_dict, dict):
        optimized_dict = {}
    optimized = PromptData(
        role=optimized_dict.get("role"),
        task=optimized_dict.get("task") or "",
        context=optimized_dict.get("context"),
        constraints=optimized_dict.get("constraints"),
        output_format=optimized_dict.get("output_format"),
        examples=optimized_dict.get("examples"),
    )
    return PromptOptimizeResponse(
        engine=result.engine,
        optimized=optimized,
        optimized_markdown=result.optimized_markdown,
        notes=result.notes,
    )


@app.post("/optimize/llm", response_model=PromptOptimizeResponse)
def optimize_prompt_llm(data: PromptData, db: Session = Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> PromptOptimizeResponse:
    logger.info("optimize.llm.start")
    result = optimize_with_llm(data.model_dump(), get_personal_config(db, current_user))
    logger.info("optimize.llm.done engine={}", result.engine)
    optimized_dict = result.optimized_fields
    if not isinstance(optimized_dict, dict):
        optimized_dict = {}
    optimized = PromptData(
        role=optimized_dict.get("role"),
        task=optimized_dict.get("task") or "",
        context=optimized_dict.get("context"),
        constraints=optimized_dict.get("constraints"),
        output_format=optimized_dict.get("output_format"),
        examples=optimized_dict.get("examples"),
    )
    return PromptOptimizeResponse(
        engine=result.engine,
        optimized=optimized,
        optimized_markdown=result.optimized_markdown,
        notes=result.notes,
    )


@app.get("/optimize/config", response_model=OptimizeConfigOut)
def get_optimize_config(db: Session = Depends(get_db), current_user: User = Depends(auth_service.get_current_user)) -> OptimizeConfigOut:
    cfg = get_personal_config(db, current_user)
    logger.info(
        "optimize.config.get effective_model_id={} effective_gp_profile={} effective_llm_model={}",
        cfg.get("effective_model_id"),
        cfg.get("effective_gp_profile"),
        cfg.get("effective_llm_model"),
    )
    return OptimizeConfigOut(**cfg)


@app.put("/optimize/config", response_model=OptimizeConfigOut)
def update_optimize_config(data: OptimizeConfigUpdate, db: Session = Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> OptimizeConfigOut:
    logger.info(
        "optimize.config.update clear_model_id={} model_id={} gp_profile={} llm_model={} rounds={}",
        data.clear_model_id,
        data.model_id,
        data.gp_profile,
        data.llm_model,
        data.rounds,
    )
    cfg = auth_service.update_personal_config(db, current_user, data.model_dump())
    return OptimizeConfigOut(**cfg)


@app.get("/optimize/providers/{provider}/models", response_model=list[str])
def get_provider_models(
    provider: str,
    base_url: str | None = Query(None, description="Optional provider base URL override"),
    api_token: str | None = Query(None, description="Optional API token for authentication"),
    timeout_seconds: int = Query(5, ge=1, le=30, description="Timeout in seconds for provider model discovery"),
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[str]:
    models = list_available_llm_models(
        provider,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        api_token=api_token,
        config_override=get_personal_config(db, current_user),
    )
    return models
