from sqlalchemy import Column, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, relationship

from database import Base

prompt_tags = Table(
    "prompt_tags",
    Base.metadata,
    Column("prompt_id", ForeignKey("prompts.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

class Prompt(Base):
    __tablename__ = "prompts"
    __table_args__ = (UniqueConstraint("name", "project", name="uq_prompt_name_project"),)

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)  # type: ignore[assignment]
    name: Mapped[str] = Column(String, index=True)  # type: ignore[assignment]
    project: Mapped[str] = Column(String, index=True)  # type: ignore[assignment]

    versions: Mapped[list["PromptVersion"]] = relationship("PromptVersion", back_populates="prompt", cascade="all, delete-orphan")
    tags: Mapped[list["Tag"]] = relationship("Tag", secondary=prompt_tags, back_populates="prompts")


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
    role: Mapped[str | None] = Column(String, nullable=True)  # type: ignore[assignment]
    task: Mapped[str] = Column(Text, nullable=False)  # type: ignore[assignment]
    context: Mapped[str | None] = Column(Text, nullable=True)  # type: ignore[assignment]
    constraints: Mapped[str | None] = Column(Text, nullable=True)  # type: ignore[assignment]
    output_format: Mapped[str | None] = Column(Text, nullable=True)  # type: ignore[assignment]
    examples: Mapped[str | None] = Column(Text, nullable=True)  # type: ignore[assignment]

    prompt: Mapped["Prompt"] = relationship("Prompt", back_populates="versions")
