from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Prompt, PromptVersion, Tag


def has_duplicate_prompt_version_content(
    db: Session,
    *,
    role: str | None,
    task: str,
    context: str | None,
    constraints: str | None,
    output_format: str | None,
    examples: str | None,
) -> bool:
    query = db.query(PromptVersion)

    filters = {
        PromptVersion.role: role,
        PromptVersion.task: task,
        PromptVersion.context: context,
        PromptVersion.constraints: constraints,
        PromptVersion.output_format: output_format,
        PromptVersion.examples: examples,
    }

    for column, value in filters.items():
        query = query.filter(column.is_(None)) if value is None else query.filter(column == value)

    return bool(db.query(query.exists()).scalar())


def normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    return sorted({tag.strip().lower() for tag in tags if tag and tag.strip()})


def get_or_create_tags(db: Session, tags: list[str]) -> list[Tag]:
    if not tags:
        return []

    existing = db.query(Tag).filter(Tag.name.in_(tags)).all()
    existing_names = {tag.name for tag in existing}

    new_tags = [Tag(name=tag_name) for tag_name in tags if tag_name not in existing_names]
    if new_tags:
        db.add_all(new_tags)
        db.flush()

    return [*existing, *new_tags]


def create_prompt(
    db: Session,
    name: str,
    project: str,
    task: str,
    role: str | None = None,
    context: str | None = None,
    constraints: str | None = None,
    output_format: str | None = None,
    examples: str | None = None,
    tags: list[str] | None = None,
) -> Prompt:
    if has_duplicate_prompt_version_content(
        db,
        role=role,
        task=task,
        context=context,
        constraints=constraints,
        output_format=output_format,
        examples=examples,
    ):
        raise ValueError("Duplicate prompt version content is not allowed")

    normalized_tags = normalize_tags(tags)
    db_tags = get_or_create_tags(db, normalized_tags)

    prompt = Prompt(name=name, project=project)
    prompt.tags = db_tags
    db.add(prompt)
    db.flush()
    db.refresh(prompt)

    version = PromptVersion(
        prompt_id=prompt.id,
        version=1,
        role=role,
        task=task,
        context=context,
        constraints=constraints,
        output_format=output_format,
        examples=examples,
    )
    db.add(version)
    db.commit()

    return prompt


def get_prompt(db: Session, name: str, project: str) -> Prompt | None:
    return db.query(Prompt).filter_by(name=name, project=project).first()


def _build_prompt_list_query(db: Session, project: str | None = None, tag: str | None = None):  # type: ignore[no-untyped-def]
    query = db.query(Prompt)

    if project:
        query = query.filter(Prompt.project == project)

    if tag:
        query = query.join(Prompt.tags).filter(Tag.name == tag.strip().lower())

    return query


def count_prompts(db: Session, project: str | None = None, tag: str | None = None) -> int:
    query = _build_prompt_list_query(db, project=project, tag=tag)
    result = query.distinct().count()
    return int(result) if result is not None else 0


def list_prompts(
    db: Session,
    project: str | None = None,
    tag: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[Prompt]:
    query = _build_prompt_list_query(db, project=project, tag=tag).order_by(Prompt.project.asc(), Prompt.name.asc())

    if offset is not None:
        query = query.offset(max(0, offset))
    if limit is not None:
        query = query.limit(max(1, limit))

    results = query.all()
    return list(results) if results else []


def get_latest_version(db: Session, prompt_id: int) -> PromptVersion | None:
    return (
        db.query(PromptVersion)
        .filter_by(prompt_id=prompt_id)
        .order_by(PromptVersion.version.desc())
        .first()
    )


def add_version(
    db: Session,
    prompt_id: int,
    task: str,
    role: str | None = None,
    context: str | None = None,
    constraints: str | None = None,
    output_format: str | None = None,
    examples: str | None = None,
) -> PromptVersion:
    if has_duplicate_prompt_version_content(
        db,
        role=role,
        task=task,
        context=context,
        constraints=constraints,
        output_format=output_format,
        examples=examples,
    ):
        raise ValueError("Duplicate prompt version content is not allowed")

    latest = get_latest_version(db, prompt_id)
    if not latest:
        raise ValueError(f"No latest version found for prompt {prompt_id}")
    new_version = PromptVersion(
        prompt_id=prompt_id,
        version=latest.version + 1,
        role=role,
        task=task,
        context=context,
        constraints=constraints,
        output_format=output_format,
        examples=examples,
    )
    db.add(new_version)
    db.commit()
    return new_version


def set_prompt_tags(db: Session, prompt: Prompt, tags: list[str] | None) -> Prompt:
    normalized_tags = normalize_tags(tags)
    db_tags = get_or_create_tags(db, normalized_tags)
    prompt.tags = db_tags
    db.commit()
    db.refresh(prompt)
    return prompt


def get_specific_version(db: Session, prompt_id: int, version: int) -> PromptVersion | None:
    return (
        db.query(PromptVersion)
        .filter_by(prompt_id=prompt_id, version=version)
        .first()
    )


def list_versions(db: Session, prompt_id: int) -> list[PromptVersion]:
    results = (
        db.query(PromptVersion)
        .filter_by(prompt_id=prompt_id)
        .order_by(PromptVersion.version.asc())
        .all()
    )
    return list(results) if results else []


def search_prompts_by_tags(
    db: Session,
    tags: list[str],
    mode: str = "or",
    project: str | None = None,
) -> list[Prompt]:
    """Return prompts matching tags with AND (all tags required) or OR (any tag) semantics."""
    normalized = normalize_tags(tags)
    if not normalized:
        return []

    query = db.query(Prompt)

    if project:
        query = query.filter(Prompt.project == project)

    if mode == "and":
        # Prompt must have every requested tag: count distinct matching tags == len(normalized)
        subq = (
            db.query(Prompt.id)
            .join(Prompt.tags)
            .filter(Tag.name.in_(normalized))
            .group_by(Prompt.id)
            .having(func.count(func.distinct(Tag.id)) == len(normalized))
        )
        query = query.filter(Prompt.id.in_(subq))
    else:
        # OR: at least one tag matches
        query = query.join(Prompt.tags).filter(Tag.name.in_(normalized)).distinct()

    results = query.order_by(Prompt.project.asc(), Prompt.name.asc()).all()
    return list(results) if results else []
