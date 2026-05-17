from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from models import Config, Project, ProjectAccess, Prompt, PromptVersion, Role, Tag, User

DEFAULT_ROLE_NAMES = ("admin", "developer")


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


def normalize_project_name(project: str) -> str:
    return project.strip()


def get_project_by_name(db: Session, name: str) -> Project | None:
    normalized_name = normalize_project_name(name)
    if not normalized_name:
        return None
    return db.query(Project).filter(func.lower(Project.name) == normalized_name.lower()).first()


def get_project_by_id(db: Session, project_id: int) -> Project | None:
    return db.query(Project).filter(Project.id == project_id).first()


def list_roles(db: Session) -> list[Role]:
    return list(db.query(Role).order_by(Role.name.asc()).all())


def get_role_by_name(db: Session, name: str) -> Role | None:
    normalized_name = (name or "").strip().lower()
    if not normalized_name:
        return None
    return db.query(Role).filter(func.lower(Role.name) == normalized_name).first()


def ensure_default_roles(db: Session) -> list[Role]:
    existing = db.query(Role).filter(Role.name.in_(DEFAULT_ROLE_NAMES)).all()
    existing_names = {role.name for role in existing}
    for role_name in DEFAULT_ROLE_NAMES:
        if role_name not in existing_names:
            db.add(Role(name=role_name))
    db.commit()
    return list_roles(db)


def list_projects(db: Session) -> list[Project]:
    return list(db.query(Project).order_by(Project.name.asc()).all())


def create_project(db: Session, name: str) -> Project:
    normalized_name = normalize_project_name(name)
    existing = get_project_by_name(db, normalized_name)
    if existing:
        raise ValueError("Project already exists")
    project = Project(name=normalized_name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def update_project(db: Session, project: Project, *, name: str) -> Project:
    normalized_name = normalize_project_name(name)
    existing = get_project_by_name(db, normalized_name)
    if existing and existing.id != project.id:
        raise ValueError("Project already exists")
    project.name = normalized_name
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project: Project) -> None:
    db.delete(project)
    db.commit()


def get_or_create_project(db: Session, name: str) -> Project:
    normalized_name = normalize_project_name(name)
    existing = get_project_by_name(db, normalized_name)
    if existing:
        return existing
    project = Project(name=normalized_name)
    db.add(project)
    db.flush()
    return project


def get_or_create_projects(db: Session, names: list[str]) -> list[Project]:
    normalized_names = sorted({normalize_project_name(name) for name in names if name and normalize_project_name(name)})
    if not normalized_names:
        return []

    existing = db.query(Project).filter(Project.name.in_(normalized_names)).all()
    existing_names = {project.name for project in existing}
    new_projects = [Project(name=name) for name in normalized_names if name not in existing_names]
    if new_projects:
        db.add_all(new_projects)
        db.flush()
    return [*existing, *new_projects]


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
    project_record = get_or_create_project(db, project)

    prompt = Prompt(name=name, project_ref=project_record)
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


def get_prompt(db: Session, name: str, project: str, allowed_projects: list[str] | None = None) -> Prompt | None:
    query = (
        db.query(Prompt)
        .join(Prompt.project_ref)
        .options(joinedload(Prompt.project_ref))
        .filter(Prompt.name == name, Project.name == normalize_project_name(project))
    )
    if allowed_projects is not None:
        if not allowed_projects:
            return None
        query = query.filter(Project.name.in_(allowed_projects))
    return query.first()


def delete_prompt(db: Session, prompt: Prompt) -> None:
    db.delete(prompt)
    db.commit()


def _build_prompt_list_query(
    db: Session,
    project: str | None = None,
    tag: str | None = None,
    allowed_projects: list[str] | None = None,
):  # type: ignore[no-untyped-def]
    query = db.query(Prompt)
    query = query.join(Prompt.project_ref).options(joinedload(Prompt.project_ref))

    if allowed_projects is not None:
        if not allowed_projects:
            return query.filter(False)
        query = query.filter(Project.name.in_(allowed_projects))

    if project:
        query = query.filter(Project.name == normalize_project_name(project))

    if tag:
        query = query.join(Prompt.tags).filter(Tag.name == tag.strip().lower())

    return query


def count_prompts(db: Session, project: str | None = None, tag: str | None = None, allowed_projects: list[str] | None = None) -> int:
    query = _build_prompt_list_query(db, project=project, tag=tag, allowed_projects=allowed_projects)
    result = query.distinct().count()
    return int(result) if result is not None else 0


def list_prompts(
    db: Session,
    project: str | None = None,
    tag: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    allowed_projects: list[str] | None = None,
) -> list[Prompt]:
    query = _build_prompt_list_query(db, project=project, tag=tag, allowed_projects=allowed_projects).order_by(Project.name.asc(), Prompt.name.asc())

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
    latest = get_latest_version(db, prompt_id)
    if not latest:
        raise ValueError(f"No latest version found for prompt {prompt_id}")

    # Check if content is identical to latest version; if so, return latest without creating new version
    if (
        latest.role == role
        and latest.task == task
        and latest.context == context
        and latest.constraints == constraints
        and latest.output_format == output_format
        and latest.examples == examples
    ):
        return latest

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
    allowed_projects: list[str] | None = None,
) -> list[Prompt]:
    """Return prompts matching tags with AND (all tags required) or OR (any tag) semantics."""
    normalized = normalize_tags(tags)
    if not normalized:
        return []

    query = db.query(Prompt)
    query = query.join(Prompt.project_ref).options(joinedload(Prompt.project_ref))

    if allowed_projects is not None:
        if not allowed_projects:
            return []
        query = query.filter(Project.name.in_(allowed_projects))

    if project:
        query = query.filter(Project.name == normalize_project_name(project))

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

    results = query.order_by(Project.name.asc(), Prompt.name.asc()).all()
    return list(results) if results else []


def list_users(db: Session) -> list[User]:
    return list(
        db.query(User)
        .options(joinedload(User.role_ref), joinedload(User.project_access).joinedload(ProjectAccess.project_ref))
        .order_by(User.username.asc())
        .all()
    )


def get_user_by_username(db: Session, username: str) -> User | None:
    return (
        db.query(User)
        .options(joinedload(User.role_ref), joinedload(User.project_access).joinedload(ProjectAccess.project_ref))
        .filter(func.lower(User.username) == username.strip().lower())
        .first()
    )


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return (
        db.query(User)
        .options(joinedload(User.role_ref), joinedload(User.project_access).joinedload(ProjectAccess.project_ref))
        .filter(User.id == user_id)
        .first()
    )


def get_or_create_user_config(db: Session, user_id: int) -> Config:
    config = db.query(Config).filter(Config.user_id == user_id).first()
    if config:
        return config
    config = Config(user_id=user_id)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def set_user_projects(db: Session, user: User, projects: list[str] | None) -> User:
    db_projects = get_or_create_projects(db, projects or [])
    user.project_access.clear()
    for project in sorted(db_projects, key=lambda item: item.name.lower()):
        user.project_access.append(ProjectAccess(project_ref=project))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_user(
    db: Session,
    *,
    username: str,
    password_hash_encrypted: str,
    role: str,
    is_active: bool,
    projects: list[str] | None = None,
) -> User:
    role_record = get_role_by_name(db, role)
    if role_record is None:
        raise ValueError("Invalid role")
    user = User(username=username.strip(), password_hash_encrypted=password_hash_encrypted, role_ref=role_record, is_active=is_active)
    db.add(user)
    db.flush()
    db.add(Config(user_id=user.id))
    db.commit()
    db.refresh(user)
    return set_user_projects(db, user, projects)


def update_user(
    db: Session,
    user: User,
    *,
    username: str | None = None,
    password_hash_encrypted: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    projects: list[str] | None = None,
) -> User:
    if username is not None:
        user.username = username.strip()
    if password_hash_encrypted is not None:
        user.password_hash_encrypted = password_hash_encrypted
    if role is not None:
        role_record = get_role_by_name(db, role)
        if role_record is None:
            raise ValueError("Invalid role")
        user.role_ref = role_record
    if is_active is not None:
        user.is_active = is_active
    db.add(user)
    db.commit()
    db.refresh(user)
    if projects is not None:
        return set_user_projects(db, user, projects)
    return user


def delete_user(db: Session, user: User) -> None:
    db.delete(user)
    db.commit()
