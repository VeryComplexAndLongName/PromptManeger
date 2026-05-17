from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Table, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, relationship

from database import Base

prompt_tags = Table(
    "prompt_tags",
    Base.metadata,
    Column("prompt_id", ForeignKey("prompts.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("name", name="uq_projects_name"),
        CheckConstraint("trim(name) <> ''", name="ck_projects_name_not_blank"),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    name: Mapped[str] = Column(String, nullable=False, index=True)  # type: ignore[assignment]

    prompts: Mapped[list["Prompt"]] = relationship("Prompt", back_populates="project_ref", cascade="all, delete-orphan")
    project_access: Mapped[list["ProjectAccess"]] = relationship("ProjectAccess", back_populates="project_ref", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("name", name="uq_roles_name"),
        CheckConstraint("trim(name) <> ''", name="ck_roles_name_not_blank"),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    name: Mapped[str] = Column(String, nullable=False, index=True)  # type: ignore[assignment]

    users: Mapped[list["User"]] = relationship("User", back_populates="role_ref")


class Prompt(Base):
    __tablename__ = "prompts"
    __table_args__ = (
        UniqueConstraint("name", "project_id", name="uq_prompt_name_project_id"),
        CheckConstraint("trim(name) <> ''", name="ck_prompts_name_not_blank"),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    name: Mapped[str] = Column(String, index=True, nullable=False)  # type: ignore[assignment]
    project_id: Mapped[int] = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)  # type: ignore[assignment]
    created_at: Mapped[DateTime] = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # type: ignore[assignment]
    updated_at: Mapped[DateTime] = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # type: ignore[assignment]
    created_by_id: Mapped[int | None] = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)  # type: ignore[assignment]
    updated_by_id: Mapped[int | None] = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)  # type: ignore[assignment]

    project_ref: Mapped["Project"] = relationship("Project", back_populates="prompts")
    versions: Mapped[list["PromptVersion"]] = relationship("PromptVersion", back_populates="prompt", cascade="all, delete-orphan")
    tags: Mapped[list["Tag"]] = relationship("Tag", secondary=prompt_tags, back_populates="prompts")
    created_by_ref: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id], back_populates="created_prompts")
    updated_by_ref: Mapped["User | None"] = relationship("User", foreign_keys=[updated_by_id], back_populates="updated_prompts")

    @property
    def project(self) -> str:
        return self.project_ref.name


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        CheckConstraint("trim(username) <> ''", name="ck_users_username_not_blank"),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    username: Mapped[str] = Column(String, nullable=False, index=True)  # type: ignore[assignment]
    password_hash_encrypted: Mapped[str] = Column(Text, nullable=False)  # type: ignore[assignment]
    role_id: Mapped[int] = Column(Integer, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True)  # type: ignore[assignment]
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True)  # type: ignore[assignment]

    role_ref: Mapped["Role"] = relationship("Role", back_populates="users")
    config: Mapped["Config | None"] = relationship("Config", back_populates="user", cascade="all, delete-orphan", uselist=False)
    project_access: Mapped[list["ProjectAccess"]] = relationship("ProjectAccess", back_populates="user", cascade="all, delete-orphan")
    created_prompts: Mapped[list["Prompt"]] = relationship("Prompt", foreign_keys="Prompt.created_by_id", back_populates="created_by_ref")
    updated_prompts: Mapped[list["Prompt"]] = relationship("Prompt", foreign_keys="Prompt.updated_by_id", back_populates="updated_by_ref")
    created_prompt_versions: Mapped[list["PromptVersion"]] = relationship("PromptVersion", foreign_keys="PromptVersion.created_by_id", back_populates="created_by_ref")

    @property
    def role(self) -> str:
        return self.role_ref.name


class ProjectAccess(Base):
    __tablename__ = "project_access"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", name="uq_project_access_user_project_id"),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    user_id: Mapped[int] = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)  # type: ignore[assignment]
    project_id: Mapped[int] = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)  # type: ignore[assignment]

    user: Mapped["User"] = relationship("User", back_populates="project_access")
    project_ref: Mapped["Project"] = relationship("Project", back_populates="project_access")

    @property
    def project(self) -> str:
        return self.project_ref.name


class Config(Base):
    __tablename__ = "configs"
    __table_args__ = (UniqueConstraint("user_id", name="uq_configs_user_id"),)

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    user_id: Mapped[int] = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)  # type: ignore[assignment]
    llm_provider: Mapped[str | None] = Column(String, nullable=True)  # type: ignore[assignment]
    llm_model: Mapped[str | None] = Column(String, nullable=True)  # type: ignore[assignment]
    llm_base_url: Mapped[str | None] = Column(String, nullable=True)  # type: ignore[assignment]
    llm_timeout_seconds: Mapped[int | None] = Column(Integer, nullable=True)  # type: ignore[assignment]
    llm_api_token_encrypted: Mapped[str | None] = Column(Text, nullable=True)  # type: ignore[assignment]

    user: Mapped["User"] = relationship("User", back_populates="config")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    name: Mapped[str] = Column(String, unique=True, index=True, nullable=False)  # type: ignore[assignment]

    prompts: Mapped[list["Prompt"]] = relationship("Prompt", secondary=prompt_tags, back_populates="tags")


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("prompt_id", "version", name="uq_prompt_version"),
        UniqueConstraint(
            "role",
            "task",
            "context",
            "constraints",
            "output_format",
            "examples",
            name="uq_prompt_version_content_fields",
        ),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    prompt_id: Mapped[int] = Column(Integer, ForeignKey("prompts.id", ondelete="CASCADE"))  # type: ignore[assignment]
    version: Mapped[int] = Column(Integer)  # type: ignore[assignment]
    created_at: Mapped[DateTime] = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # type: ignore[assignment]
    created_by_id: Mapped[int | None] = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)  # type: ignore[assignment]
    role: Mapped[str | None] = Column(String, nullable=True)  # type: ignore[assignment]
    task: Mapped[str] = Column(Text, nullable=False)  # type: ignore[assignment]
    context: Mapped[str | None] = Column(Text, nullable=True)  # type: ignore[assignment]
    constraints: Mapped[str | None] = Column(Text, nullable=True)  # type: ignore[assignment]
    output_format: Mapped[str | None] = Column(Text, nullable=True)  # type: ignore[assignment]
    examples: Mapped[str | None] = Column(Text, nullable=True)  # type: ignore[assignment]

    prompt: Mapped["Prompt"] = relationship("Prompt", back_populates="versions")
    created_by_ref: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id], back_populates="created_prompt_versions")
