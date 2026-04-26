import os
import sys
from collections.abc import Iterator
from time import perf_counter
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy.orm import Session

import crud
from database import SessionLocal
from models import Prompt
from optimizer_service import (
    clear_runtime_model_id,
    get_runtime_optimizer_config,
    optimize_with_greaterprompt,
    optimize_with_llm,
    set_runtime_optimizer_config,
)
from schemas import (
    OptimizeConfigOut,
    OptimizeConfigUpdate,
    PromptCreate,
    PromptData,
    PromptOptimizeResponse,
    PromptOut,
    PromptTagsUpdate,
    PromptUpdate,
    PromptVersionOut,
)

app = FastAPI(title="Local Prompt Manager")
app.mount("/ui", StaticFiles(directory="ui"), name="ui")


def configure_logging() -> None:
    os.makedirs("logs", exist_ok=True)
    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        enqueue=False,
        backtrace=False,
        diagnose=False,
        colorize=False,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {message}",
    )
    logger.add(
        "logs/app.log",
        level="DEBUG",
        rotation="10 MB",
        retention="10 days",
        enqueue=True,
        backtrace=True,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}",
    )


configure_logging()
logger.info("logging.configured sinks=console+file")


@app.middleware("http")
async def log_requests(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
    start = perf_counter()
    client = request.client.host if request.client else "unknown"
    logger.info(
        "request.start method={} path={} query={} client={}",
        request.method,
        request.url.path,
        request.url.query,
        client,
    )
    try:
        response: Response = await call_next(request)
    except Exception:
        duration_ms = (perf_counter() - start) * 1000
        logger.exception(
            "request.error method={} path={} duration_ms={:.2f}",
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = (perf_counter() - start) * 1000
    logger.info(
        "request.end method={} path={} status={} duration_ms={:.2f}",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def to_prompt_out(db: Session, prompt: Prompt) -> PromptOut:
    latest = crud.get_latest_version(db, prompt.id)
    if not latest:
        raise ValueError(f"No version found for prompt {prompt.id}")
    return PromptOut(
        name=prompt.name,
        project=prompt.project,
        tags=[tag.name for tag in prompt.tags],
        latest_version=latest.version,
        role=latest.role,
        task=latest.task,
        context=latest.context,
        constraints=latest.constraints,
        output_format=latest.output_format,
        examples=latest.examples,
    )


@app.get("/", include_in_schema=False)
def serve_ui() -> FileResponse:
    return FileResponse("ui/html/index.html")


@app.get("/prompts/search", response_model=list[PromptOut])
def search_prompts(
    tags: list[str] = Query(..., description="Tags to filter by (repeat for multiple)"),
    mode: Literal["and", "or"] = Query("or", description="'and' requires all tags; 'or' requires any tag"),
    project: str | None = None,
    db: Session = Depends(get_db),
) -> list[PromptOut]:
    prompts = crud.search_prompts_by_tags(db, tags=tags, mode=mode, project=project)
    return [to_prompt_out(db, p) for p in prompts]


@app.get("/prompts", response_model=list[PromptOut])
def list_prompts(
    response: Response,
    project: str | None = None,
    tag: str | None = None,
    limit: int | None = Query(None, ge=1, description="Optional max number of prompts to return"),
    offset: int | None = Query(None, ge=0, description="Optional number of prompts to skip"),
    db: Session = Depends(get_db),
) -> list[PromptOut]:
    total_count = crud.count_prompts(db, project=project, tag=tag)
    response.headers["X-Total-Count"] = str(total_count)
    prompts = crud.list_prompts(db, project=project, tag=tag, limit=limit, offset=offset)
    return [to_prompt_out(db, prompt) for prompt in prompts]


@app.post("/prompts", response_model=PromptOut)
def create_prompt(data: PromptCreate, db: Session = Depends(get_db)) -> PromptOut:
    logger.info("prompt.create name={} project={}", data.name, data.project)
    prompt = crud.get_prompt(db, data.name, data.project)
    if prompt:
        logger.warning("prompt.create.duplicate name={} project={}", data.name, data.project)
        raise HTTPException(400, "Prompt already exists")

    try:
        prompt = crud.create_prompt(
            db,
            data.name,
            data.project,
            task=data.task,
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
def get_prompt(project: str, name: str, db: Session = Depends(get_db)) -> PromptOut:
    prompt = crud.get_prompt(db, name, project)
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    return to_prompt_out(db, prompt)


@app.put("/prompts/{project}/{name}", response_model=PromptVersionOut)
def update_prompt(project: str, name: str, data: PromptUpdate, db: Session = Depends(get_db)) -> PromptVersionOut:
    logger.info("prompt.update project={} name={}", project, name)
    prompt = crud.get_prompt(db, name, project)
    if not prompt:
        logger.warning("prompt.update.not_found project={} name={}", project, name)
        raise HTTPException(404, "Prompt not found")

    if data.tags is not None:
        crud.set_prompt_tags(db, prompt, data.tags)

    try:
        new_version = crud.add_version(
            db,
            prompt.id,
            task=data.task,
            role=data.role,
            context=data.context,
            constraints=data.constraints,
            output_format=data.output_format,
            examples=data.examples,
        )
    except ValueError as exc:
        logger.warning("prompt.update.duplicate_content project={} name={}", project, name)
        raise HTTPException(409, str(exc)) from exc
    return PromptVersionOut(
        version=new_version.version,
        role=new_version.role,
        task=new_version.task,
        context=new_version.context,
        constraints=new_version.constraints,
        output_format=new_version.output_format,
        examples=new_version.examples,
    )


@app.put("/prompts/{project}/{name}/tags", response_model=PromptOut)
def update_prompt_tags(project: str, name: str, data: PromptTagsUpdate, db: Session = Depends(get_db)) -> PromptOut:
    prompt = crud.get_prompt(db, name, project)
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    prompt = crud.set_prompt_tags(db, prompt, data.tags)
    return to_prompt_out(db, prompt)


@app.get("/prompts/{project}/{name}/versions", response_model=list[PromptVersionOut])
def list_versions(project: str, name: str, db: Session = Depends(get_db)) -> list[PromptVersionOut]:
    prompt = crud.get_prompt(db, name, project)
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    versions = crud.list_versions(db, prompt.id)
    return [
        PromptVersionOut(
            version=v.version,
            role=v.role,
            task=v.task,
            context=v.context,
            constraints=v.constraints,
            output_format=v.output_format,
            examples=v.examples,
        )
        for v in versions
    ]


@app.get("/prompts/{project}/{name}/versions/{version}", response_model=PromptVersionOut)
def get_version(project: str, name: str, version: int, db: Session = Depends(get_db)) -> PromptVersionOut:
    prompt = crud.get_prompt(db, name, project)
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    v = crud.get_specific_version(db, prompt.id, version)
    if not v:
        raise HTTPException(404, "Version not found")

    return PromptVersionOut(
        version=v.version,
        role=v.role,
        task=v.task,
        context=v.context,
        constraints=v.constraints,
        output_format=v.output_format,
        examples=v.examples,
    )


@app.post("/optimize/greaterprompt", response_model=PromptOptimizeResponse)
def optimize_prompt(data: PromptData) -> PromptOptimizeResponse:
    logger.info("optimize.greaterprompt.start")
    result = optimize_with_greaterprompt(data.model_dump())
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
def optimize_prompt_llm(data: PromptData) -> PromptOptimizeResponse:
    logger.info("optimize.llm.start")
    result = optimize_with_llm(data.model_dump())
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
def get_optimize_config() -> OptimizeConfigOut:
    cfg = get_runtime_optimizer_config()
    logger.info(
        "optimize.config.get effective_model_id={} effective_gp_profile={} effective_llm_model={}",
        cfg.get("effective_model_id"),
        cfg.get("effective_gp_profile"),
        cfg.get("effective_llm_model"),
    )
    return OptimizeConfigOut(**cfg)


@app.put("/optimize/config", response_model=OptimizeConfigOut)
def update_optimize_config(data: OptimizeConfigUpdate) -> OptimizeConfigOut:
    logger.info(
        "optimize.config.update clear_model_id={} model_id={} gp_profile={} llm_model={} rounds={}",
        data.clear_model_id,
        data.model_id,
        data.gp_profile,
        data.llm_model,
        data.rounds,
    )
    if data.clear_model_id:
        cfg = clear_runtime_model_id()
        if data.rounds is not None:
            cfg = set_runtime_optimizer_config(rounds=data.rounds)
        if (
            data.gp_profile is not None
            or data.llm_provider is not None
            or data.llm_model is not None
            or data.llm_base_url is not None
            or data.llm_timeout_seconds is not None
        ):
            cfg = set_runtime_optimizer_config(
                gp_profile=data.gp_profile,
                llm_provider=data.llm_provider,
                llm_model=data.llm_model,
                llm_base_url=data.llm_base_url,
                llm_timeout_seconds=data.llm_timeout_seconds,
            )
        return OptimizeConfigOut(**cfg)

    cfg = set_runtime_optimizer_config(
        model_id=data.model_id,
        rounds=data.rounds,
        gp_profile=data.gp_profile,
        llm_provider=data.llm_provider,
        llm_model=data.llm_model,
        llm_base_url=data.llm_base_url,
        llm_timeout_seconds=data.llm_timeout_seconds,
    )
    return OptimizeConfigOut(**cfg)
