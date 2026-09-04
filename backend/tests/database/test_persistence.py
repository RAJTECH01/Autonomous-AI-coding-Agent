"""Database tests against a real engine, real schema and real constraints.

No repository is mocked. Each test drives the actual SQLAlchemy models and
repositories, so constraint violations, soft deletes, cascades and pagination are
verified by the database rather than asserted about in the abstract.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.security import get_password_hash
from app.domain.entities.agent import (
    AgentError,
    AgentPlan,
    AgentRun,
    AgentState,
    AgentStep,
    ToolCall,
    ToolResult,
)
from app.infrastructure.db.models.agent import AgentRunModel, AgentStepModel, ErrorLogModel
from app.infrastructure.db.models.project import ProjectMemberModel, ProjectModel
from app.infrastructure.db.models.task import CodingTaskModel
from app.infrastructure.db.models.user import AuthSessionModel, UserModel
from app.infrastructure.db.repositories.agent_repository import AgentRepository
from app.infrastructure.db.repositories.project_repository import ProjectRepository
from app.infrastructure.db.repositories.user_repository import UserRepository
from app.schemas.common import PageParams

pytestmark = [pytest.mark.database, pytest.mark.integration, pytest.mark.asyncio]


async def _make_user(session, email=None, role="user") -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        email=email or f"{uuid.uuid4().hex[:10]}@example.test",
        password_hash=get_password_hash("Str0ng-Passw0rd!42"),
        full_name="DB Test User",
        role=role,
    )
    session.add(user)
    await session.flush()
    return user


async def _make_project(session, owner_id, name=None) -> ProjectModel:
    slug = f"p-{uuid.uuid4().hex[:10]}"
    project = ProjectModel(
        id=uuid.uuid4(),
        owner_id=owner_id,
        name=name or slug,
        slug=slug,
        language_stack="python",
        default_branch="main",
    )
    session.add(project)
    await session.flush()
    return project


# ------------------------------------------------------------------ constraints
class TestConstraints:
    async def test_email_is_unique(self, db_session):
        await _make_user(db_session, email="duplicate@example.test")
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await _make_user(db_session, email="duplicate@example.test")
            await db_session.commit()

    async def test_project_slug_is_unique(self, db_session):
        owner = await _make_user(db_session)
        shared_slug = f"slug-{uuid.uuid4().hex[:8]}"
        for _ in range(2):
            db_session.add(
                ProjectModel(
                    id=uuid.uuid4(), owner_id=owner.id, name="same", slug=shared_slug,
                    language_stack="python", default_branch="main",
                )
            )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_a_user_cannot_be_added_to_a_project_twice(self, db_session):
        owner = await _make_user(db_session)
        member = await _make_user(db_session)
        project = await _make_project(db_session, owner.id)
        for _ in range(2):
            db_session.add(
                ProjectMemberModel(id=uuid.uuid4(), project_id=project.id, user_id=member.id, role="developer")
            )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_password_hash_is_required(self, db_session):
        db_session.add(
            UserModel(id=uuid.uuid4(), email="nohash@example.test", full_name="No Hash", role="user")
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_refresh_token_hash_is_unique(self, db_session):
        user = await _make_user(db_session)
        shared = "hash-" + uuid.uuid4().hex
        for _ in range(2):
            db_session.add(
                AuthSessionModel(
                    id=uuid.uuid4(), user_id=user.id, refresh_token_hash=shared,
                    expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                )
            )
        with pytest.raises(IntegrityError):
            await db_session.commit()


# --------------------------------------------------------------- soft deletes
class TestSoftDelete:
    async def test_soft_deleted_user_is_excluded_from_lookup(self, db_session):
        repo = UserRepository(db_session)
        user = await _make_user(db_session, email="soft@example.test")
        await db_session.commit()

        assert await repo.get_by_email("soft@example.test") is not None

        user.deleted_at = datetime.now(timezone.utc)
        await db_session.commit()

        assert await repo.get_by_email("soft@example.test") is None

    async def test_soft_deleted_row_still_exists_physically(self, db_session):
        user = await _make_user(db_session, email="tombstone@example.test")
        user.deleted_at = datetime.now(timezone.utc)
        await db_session.commit()

        found = await db_session.execute(select(UserModel).where(UserModel.email == "tombstone@example.test"))
        assert found.scalar_one().deleted_at is not None

    async def test_soft_deleted_project_is_excluded_from_listings(self, db_session):
        owner = await _make_user(db_session)
        keep = await _make_project(db_session, owner.id, name="keep")
        drop = await _make_project(db_session, owner.id, name="drop")
        drop.deleted_at = datetime.now(timezone.utc)
        await db_session.commit()

        items, total = await ProjectRepository(db_session).list_paginated(
            PageParams(page=1, page_size=50), ProjectModel.deleted_at.is_(None)
        )
        listed = {p.id for p in items}
        assert keep.id in listed
        assert drop.id not in listed


# ----------------------------------------------------------------- cascades
class TestCascades:
    async def test_deleting_a_user_removes_their_auth_sessions(self, db_session_fk):
        user = await _make_user(db_session_fk)
        db_session_fk.add(
            AuthSessionModel(
                id=uuid.uuid4(), user_id=user.id, refresh_token_hash="h-" + uuid.uuid4().hex,
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        await db_session_fk.commit()

        await db_session_fk.delete(user)
        await db_session_fk.commit()

        remaining = await db_session_fk.execute(
            select(func.count()).select_from(AuthSessionModel).where(AuthSessionModel.user_id == user.id)
        )
        assert remaining.scalar() == 0

    async def test_deleting_a_project_removes_its_members(self, db_session_fk):
        owner = await _make_user(db_session_fk)
        member = await _make_user(db_session_fk)
        project = await _make_project(db_session_fk, owner.id)
        db_session_fk.add(
            ProjectMemberModel(id=uuid.uuid4(), project_id=project.id, user_id=member.id, role="developer")
        )
        await db_session_fk.commit()

        await db_session_fk.delete(project)
        await db_session_fk.commit()

        remaining = await db_session_fk.execute(
            select(func.count()).select_from(ProjectMemberModel).where(ProjectMemberModel.project_id == project.id)
        )
        assert remaining.scalar() == 0


# --------------------------------------------------------------- transactions
class TestTransactions:
    async def test_rollback_discards_the_whole_unit_of_work(self, db_session):
        user = await _make_user(db_session, email="rollback@example.test")
        await _make_project(db_session, user.id)
        await db_session.rollback()

        found = await db_session.execute(select(UserModel).where(UserModel.email == "rollback@example.test"))
        assert found.scalar_one_or_none() is None

    async def test_failed_commit_does_not_leave_partial_state(self, db_session):
        owner = await _make_user(db_session, email="partial@example.test")
        await db_session.commit()

        # Second insert violates the unique email constraint.
        await _make_project(db_session, owner.id, name="orphan-candidate")
        db_session.add(
            UserModel(
                id=uuid.uuid4(), email="partial@example.test",
                password_hash="x", full_name="Clash", role="user",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

        projects = await db_session.execute(
            select(func.count()).select_from(ProjectModel).where(ProjectModel.name == "orphan-candidate")
        )
        assert projects.scalar() == 0


# ---------------------------------------------------------------- pagination
class TestPagination:
    async def test_pages_do_not_overlap_and_cover_everything(self, db_session):
        owner = await _make_user(db_session)
        for index in range(7):
            await _make_project(db_session, owner.id, name=f"paged-{index}")
        await db_session.commit()

        repo = ProjectRepository(db_session)
        first, total = await repo.list_paginated(PageParams(page=1, page_size=3), ProjectModel.deleted_at.is_(None))
        second, _ = await repo.list_paginated(PageParams(page=2, page_size=3), ProjectModel.deleted_at.is_(None))
        third, _ = await repo.list_paginated(PageParams(page=3, page_size=3), ProjectModel.deleted_at.is_(None))

        assert total >= 7
        assert len(first) == 3 and len(second) == 3
        ids = [p.id for p in first + second + third]
        assert len(ids) == len(set(ids)), "pages returned overlapping rows"

    async def test_page_beyond_the_end_is_empty_not_an_error(self, db_session):
        owner = await _make_user(db_session)
        await _make_project(db_session, owner.id)
        await db_session.commit()

        items, _ = await ProjectRepository(db_session).list_paginated(
            PageParams(page=500, page_size=20), ProjectModel.deleted_at.is_(None)
        )
        assert items == []


# ------------------------------------------------------- tenant scoping (IDOR)
class TestTenantScoping:
    @pytest.mark.authz
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="AUTHZ-02: list_user_projects builds an owner/member filtered statement and then "
        "discards it, calling list_paginated with only a deleted_at predicate. Every user receives "
        "every project in the database.",
    )
    async def test_list_user_projects_returns_only_the_callers_projects(self, db_session):
        alice = await _make_user(db_session)
        bob = await _make_user(db_session)
        await _make_project(db_session, alice.id, name="alice-private")
        await db_session.commit()

        items, total = await ProjectRepository(db_session).list_user_projects(
            user_id=bob.id, params=PageParams(page=1, page_size=50)
        )
        assert total == 0
        assert items == []


# ------------------------------------------------------- agent run persistence
class TestAgentRunPersistence:
    async def test_run_steps_plan_and_errors_round_trip(self, db_session):
        user = await _make_user(db_session)
        project = await _make_project(db_session, user.id)
        task = CodingTaskModel(
            id=uuid.uuid4(),
            project_id=project.id,
            creator_id=user.id,
            title="persist the run",
            requirement_prompt="add a helper",
            status="pending",
        )
        db_session.add(task)
        await db_session.flush()

        repo = AgentRepository(db_session)
        run = AgentRun(
            id=str(uuid.uuid4()),
            task_id=str(task.id),
            state=AgentState.RECEIVED,
            initiator_id=str(user.id),
            started_at=datetime.now(timezone.utc),
        )
        await repo.create_run(run)

        step = AgentStep(
            id=str(uuid.uuid4()),
            run_id=run.id,
            step_number=1,
            from_state=AgentState.RECEIVED,
            to_state=AgentState.ANALYZING,
            step_type="analyzing",
            thought_process={"action": "analyse"},
        )
        await repo.create_step(step)

        await repo.create_plan(
            AgentPlan(id=str(uuid.uuid4()), run_id=run.id, goals_summary="goal", plan_markdown="## Plan")
        )

        run.state = AgentState.COMPLETED
        run.current_iteration = 3
        run.total_tokens_used = 1234
        run.completed_at = datetime.now(timezone.utc)
        await repo.update_run_state(run)
        await db_session.commit()

        stored = (
            await db_session.execute(select(AgentRunModel).where(AgentRunModel.id == uuid.UUID(run.id)))
        ).scalar_one()
        assert stored.status == "COMPLETED"
        assert stored.current_iteration == 3
        assert stored.total_tokens_used == 1234
        assert stored.completed_at is not None

        steps = (
            await db_session.execute(select(AgentStepModel).where(AgentStepModel.run_id == uuid.UUID(run.id)))
        ).scalars().all()
        assert len(steps) == 1
        assert steps[0].thought_process["from_state"] == "RECEIVED"
        assert steps[0].thought_process["to_state"] == "ANALYZING"

    async def test_tool_call_and_result_are_linked(self, db_session):
        user = await _make_user(db_session)
        project = await _make_project(db_session, user.id)
        task = CodingTaskModel(
            id=uuid.uuid4(), project_id=project.id, creator_id=user.id,
            title="tools", requirement_prompt="x", status="pending",
        )
        db_session.add(task)
        await db_session.flush()

        repo = AgentRepository(db_session)
        run = AgentRun(id=str(uuid.uuid4()), task_id=str(task.id), initiator_id=str(user.id))
        await repo.create_run(run)

        call = ToolCall(id=str(uuid.uuid4()), tool_name="write_file", tool_input={"file_path": "a.py"})
        result = ToolResult(
            id=str(uuid.uuid4()), tool_call_id=call.id, stdout_summary="ok",
            exit_code=0, execution_duration_ms=12, success=True, output="ok",
        )
        stored_call = await repo.create_tool_call_and_result(call, result)
        await db_session.commit()

        assert stored_call.tool_name == "write_file"
        assert stored_call.status == "success"

    async def test_agent_errors_are_persisted_with_their_category(self, db_session):
        user = await _make_user(db_session)
        project = await _make_project(db_session, user.id)
        task = CodingTaskModel(
            id=uuid.uuid4(), project_id=project.id, creator_id=user.id,
            title="errors", requirement_prompt="x", status="pending",
        )
        db_session.add(task)
        await db_session.flush()

        repo = AgentRepository(db_session)
        run = AgentRun(id=str(uuid.uuid4()), task_id=str(task.id), initiator_id=str(user.id))
        await repo.create_run(run)
        await repo.create_error(
            AgentError(
                id=str(uuid.uuid4()), run_id=run.id, error_type="LimitExceededError",
                stack_trace="max iterations reached", category="limit_exceeded",
            )
        )
        await db_session.commit()

        errors = (
            await db_session.execute(select(ErrorLogModel).where(ErrorLogModel.run_id == uuid.UUID(run.id)))
        ).scalars().all()
        assert [e.category for e in errors] == ["limit_exceeded"]


# ------------------------------------------------------------ injection safety
class TestQueryParameterisation:
    async def test_sql_metacharacters_in_input_are_treated_as_data(self, db_session):
        """A classic injection string must be stored and matched verbatim, and
        the users table must survive."""
        payload = "robert'); drop table users;--@example.test"
        await _make_user(db_session, email=payload)
        await db_session.commit()

        repo = UserRepository(db_session)
        found = await repo.get_by_email(payload)
        assert found is not None
        assert found.email == payload

        still_there = await db_session.execute(select(func.count()).select_from(UserModel))
        assert still_there.scalar() >= 1

    async def test_like_wildcards_in_search_input_are_not_expanded_into_a_match_all(self, db_session):
        await _make_user(db_session, email="specific@example.test")
        await db_session.commit()
        repo = UserRepository(db_session)
        assert await repo.get_by_email("%@example.test") is None
