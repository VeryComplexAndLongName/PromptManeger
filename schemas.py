from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints


RequiredPromptText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PromptBase(BaseModel):
    name: RequiredPromptText
    project: RequiredPromptText
    tags: list[str] = []


class PromptCreate(PromptBase):
    role: str | None = None
    task: str
    context: str | None = None
    constraints: str | None = None
    output_format: str | None = None
    examples: str | None = None


class PromptUpdate(BaseModel):
    role: str | None = None
    task: str
    context: str | None = None
    constraints: str | None = None
    output_format: str | None = None
    examples: str | None = None
    tags: list[str] | None = None


class PromptTagsUpdate(BaseModel):
    tags: list[str]


class PromptVersionOut(BaseModel):
    version: int
    role: str | None = None
    task: str
    context: str | None = None
    constraints: str | None = None
    output_format: str | None = None
    examples: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PromptData(BaseModel):
    role: str | None = None
    task: str
    context: str | None = None
    constraints: str | None = None
    output_format: str | None = None
    examples: str | None = None


class PromptOptimizeResponse(BaseModel):
    engine: str
    optimized: PromptData
    optimized_markdown: str
    notes: list[str] = []


class OptimizeConfigUpdate(BaseModel):
    model_id: str | None = None
    rounds: int | None = None
    gp_profile: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_timeout_seconds: int | None = None
    llm_api_token: str | None = None
    clear_model_id: bool = False


class OptimizeConfigOut(BaseModel):
    runtime_model_id: str | None = None
    runtime_rounds: int | None = None
    runtime_gp_profile: str | None = None
    runtime_llm_provider: str | None = None
    runtime_llm_model: str | None = None
    runtime_llm_base_url: str | None = None
    runtime_llm_timeout_seconds: int | None = None
    runtime_has_llm_api_token: bool = False
    env_model_id: str | None = None
    env_rounds: int | None = None
    env_gp_profile: str | None = None
    env_llm_provider: str | None = None
    env_llm_model: str | None = None
    env_llm_base_url: str | None = None
    env_llm_timeout_seconds: int | None = None
    env_has_llm_api_token: bool = False
    effective_model_id: str | None = None
    effective_rounds: int
    effective_gp_profile: str
    effective_gp_optimize_config: dict[str, Any]
    effective_llm_provider: str
    effective_llm_model: str
    effective_llm_base_url: str
    effective_llm_timeout_seconds: int
    effective_has_llm_api_token: bool = False
    gradient_enabled: bool


class UserLogin(BaseModel):
    username: RequiredPromptText
    password: RequiredPromptText


class UserBootstrap(BaseModel):
    username: RequiredPromptText
    password: RequiredPromptText


class ProjectAccessUpdate(BaseModel):
    projects: list[RequiredPromptText] = []


class ProjectCreate(BaseModel):
    name: RequiredPromptText


class ProjectUpdate(BaseModel):
    name: RequiredPromptText


class ProjectOut(BaseModel):
    id: int
    name: str


class RoleOut(BaseModel):
    id: int
    name: str


class UserCreate(BaseModel):
    username: RequiredPromptText
    password: RequiredPromptText
    role: str = "developer"
    is_active: bool = True
    projects: list[RequiredPromptText] = []


class UserUpdate(BaseModel):
    username: RequiredPromptText | None = None
    password: RequiredPromptText | None = None
    role: str | None = None
    is_active: bool | None = None
    projects: list[RequiredPromptText] | None = None


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    projects: list[str] = []


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class AuthStatus(BaseModel):
    bootstrap_required: bool
    has_users: bool


class PromptOut(BaseModel):
    name: str
    project: str
    tags: list[str]
    latest_version: int
    role: str | None = None
    task: str
    context: str | None = None
    constraints: str | None = None
    output_format: str | None = None
    examples: str | None = None

    model_config = ConfigDict(from_attributes=True)
