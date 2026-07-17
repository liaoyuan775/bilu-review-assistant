from copy import deepcopy
import asyncio
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from docx import Document

from app.errors import AppError
from app.models import (
    ArtifactSummary,
    DocumentPage,
    DocumentParagraph,
    DocumentWarning,
    ManualDecision,
    ManualStatus,
    ParsedDocument,
    ReviewMode,
    ReviewResult,
    ReviewStatus,
    ReviewTask,
    RuleStatus,
    SourceType,
    TaskStatus,
)
from app.services.archive import assert_archive_ready
from app.services import review
from app.services.template_extraction import TemplateReviewOutcome
from app.services.artifacts import ArtifactStorage
from app.services import artifacts
from app import store
from app.store import SqliteTaskStore
from app.template_models import CaseExtraction, ExtractedFact, TemplateReviewIssue
from app.main import app


REQUIRED_ARTIFACTS = ["review_pdf", "follow_up_docx", "structured_json", "archive_manifest"]


def _task() -> ReviewTask:
    document = ParsedDocument(
        name="脱敏测试笔录.docx",
        format="DOCX",
        pageCount=1,
        pages=[DocumentPage(page=1, paragraphs=[
            DocumentParagraph(id="b1", text="问：测试？答：明确。", sourceType=SourceType.NATIVE_TEXT),
        ])],
        text="问：测试？答：明确。",
        sizeLabel="test",
    )
    result = ReviewResult(
        ruleId="CASE-001",
        ruleName="测试规则",
        category="CASE",
        group="CASE",
        status=RuleStatus.COVERED,
        missingFacts=[],
        evidence="明确证据",
        evidenceLocation=None,
        reason="已覆盖。",
        suggestedQuestion="",
        source="内部模板测试",
        severity="high",
    )
    return ReviewTask(
        mode=ReviewMode.QWEN,
        status=TaskStatus.COMPLETED,
        document=document,
        documentId="document-1",
        documentVersionId="version-1",
        reviewRunId="run-1",
        results=[result],
        requiredArtifacts=REQUIRED_ARTIFACTS,
        artifacts=[
            ArtifactSummary(id=f"artifact-{kind}", type=kind, filename=f"{kind}.bin", sha256="a" * 64, sizeBytes=10)
            for kind in REQUIRED_ARTIFACTS
        ],
    )


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda task: setattr(task, "status", TaskStatus.FAILED), "archive_task_incomplete"),
        (lambda task: task.failedDomains.append("case_timeline"), "archive_failed_domains"),
        (
            lambda task: task.document.warnings.append(DocumentWarning(code="media_corrupt", message="测试告警")),
            "archive_unresolved_warnings",
        ),
        (lambda task: task.artifacts.pop(), "archive_missing_artifacts"),
        (
            lambda task: task.results.__setitem__(0, task.results[0].model_copy(update={
                "status": RuleStatus.MISSING,
                "manualDecision": ManualDecision(status=ManualStatus.PENDING),
            })),
            "archive_pending_high_risk",
        ),
    ],
)
def test_archive_gates_have_precise_error_codes(mutate, expected_code):
    task = _task()
    mutate(task)

    with pytest.raises(AppError) as error:
        assert_archive_ready(task)

    assert error.value.code == expected_code


def test_acknowledged_warning_and_resolved_high_risk_issue_can_archive():
    task = _task()
    task.document.warnings.append(DocumentWarning(code="media_corrupt", message="测试告警"))
    task.acknowledgedWarnings.append("media_corrupt")
    task.results[0] = task.results[0].model_copy(update={
        "status": RuleStatus.INCOMPLETE,
        "manualDecision": ManualDecision(status=ManualStatus.RESOLVED, reason="已补问并记录明确答案。"),
    })

    assert_archive_ready(deepcopy(task))


def test_issue_action_appends_event_and_archived_task_is_read_only(tmp_path, monkeypatch):
    database = tmp_path / "reviews.db"
    monkeypatch.setattr(store, "STORE", SqliteTaskStore(database))
    task = _task()
    task.results[0] = task.results[0].model_copy(update={
        "status": RuleStatus.MISSING,
        "manualDecision": ManualDecision(status=ManualStatus.PENDING),
    })
    store.save_task(task)

    result = review.record_issue_action(
        task.id,
        "CASE-001",
        ManualStatus.RESOLVED,
        "已核对补问答案。",
        "test-operator",
    )

    assert result.manualDecision.status == ManualStatus.RESOLVED
    events = store.STORE.get_audit_snapshot(task.id)["events"]
    assert [(event["event_type"], event["actor_id"]) for event in events] == [
        ("resolved", "test-operator"),
    ]

    task = store.get_task(task.id)
    task.reviewStatus = ReviewStatus.ARCHIVED
    store.save_task(task)
    with pytest.raises(AppError) as error:
        review.record_issue_action(
            task.id,
            "CASE-001",
            ManualStatus.IGNORED,
            "不能修改。",
            "test-operator",
        )
    assert error.value.code == "review_archived"


def test_follow_up_answer_creates_version_event_and_affected_domain_rerun(tmp_path, monkeypatch):
    database = tmp_path / "reviews.db"
    monkeypatch.setattr(store, "STORE", SqliteTaskStore(database))
    task = _task()
    task.results[0] = task.results[0].model_copy(update={
        "status": RuleStatus.MISSING,
        "manualDecision": ManualDecision(status=ManualStatus.SUPPLEMENTED, reason="请补充报案原因。"),
    })
    task.extractionPayload = CaseExtraction().model_dump(mode="json")
    store.save_task(task)
    task.documentId = store.STORE.save_document(
        task.id,
        filename=task.document.name,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        sha256="a" * 64,
        original_path="test/original.docx",
    )
    task.documentVersionId = store.STORE.save_document_version(
        task.documentId,
        content_sha256="a" * 64,
        parsed_payload=task.document.model_dump(mode="json"),
    )
    store.save_task(task)
    resolved_result = task.results[0].model_copy(update={"status": RuleStatus.COVERED})
    outcome = TemplateReviewOutcome(
        extraction=CaseExtraction(),
        issues=[],
        results=[resolved_result],
    )
    run = AsyncMock(return_value=outcome)
    monkeypatch.setattr(review, "run_template_review", run)

    updated = asyncio.run(review.record_follow_up_answer(
        task.id,
        "CASE-001",
        question="你因何事报案？",
        answer="因测试诈骗损失报案。",
        actor_id="test-operator",
    ))

    assert updated.documentVersionId != task.documentVersionId
    assert updated.results[0].manualDecision.status == ManualStatus.RESOLVED
    assert run.await_args.kwargs["domains"] == ("case_timeline",)
    snapshot = store.STORE.get_audit_snapshot(task.id)
    assert len(snapshot["versions"]) == 2
    assert snapshot["events"][-1]["event_type"] == "follow_up_answer"


def test_failed_domain_retry_restores_completed_state(tmp_path, monkeypatch):
    database = tmp_path / "reviews.db"
    monkeypatch.setattr(store, "STORE", SqliteTaskStore(database))
    task = _task()
    task.status = TaskStatus.FAILED
    task.failedDomains = ["case_timeline"]
    task.extractionPayload = CaseExtraction().model_dump(mode="json")
    store.save_task(task)
    outcome = TemplateReviewOutcome(
        extraction=CaseExtraction(),
        issues=[],
        results=task.results,
    )
    run = AsyncMock(return_value=outcome)
    monkeypatch.setattr(review, "run_template_review", run)

    updated = asyncio.run(review.retry_failed_domain(task.id, "case_timeline", "test-operator"))

    assert updated.status == TaskStatus.COMPLETED
    assert updated.failedDomains == []
    assert run.await_args.kwargs["domains"] == ("case_timeline",)
    assert store.STORE.get_audit_snapshot(task.id)["events"][-1]["event_type"] == "domain_retried"


def test_upload_persists_original_version_run_fact_issue_and_artifact(tmp_path, monkeypatch):
    database = tmp_path / "reviews.db"
    monkeypatch.setattr(store, "STORE", SqliteTaskStore(database))
    monkeypatch.setattr(artifacts, "ARTIFACT_STORAGE", ArtifactStorage(tmp_path / "artifacts"))
    task = review.create_task(ReviewMode.QWEN)
    document = Document()
    document.add_paragraph("问：你因何事报案？")
    document.add_paragraph("答：因脱敏测试诈骗报案。")
    output = BytesIO()
    document.save(output)
    result = _task().results[0]
    extraction = CaseExtraction(facts={
        "case.report_reason": ExtractedFact(value="脱敏测试诈骗", clarity="clear", evidenceAnchorIds=[]),
    })
    issue = TemplateReviewIssue(
        ruleId="CASE-001",
        ruleName="测试规则",
        group="CASE",
        status=RuleStatus.COVERED,
        reason="已覆盖。",
        suggestedQuestion="",
        severity="high",
    )
    monkeypatch.setattr(review, "run_template_review", AsyncMock(return_value=TemplateReviewOutcome(
        extraction=extraction,
        issues=[issue],
        results=[result],
    )))

    asyncio.run(review.process_upload(task.id, "脱敏测试.docx", output.getvalue()))

    saved = store.get_task(task.id)
    snapshot = store.STORE.get_audit_snapshot(task.id)
    assert saved.status == TaskStatus.COMPLETED
    assert saved.documentId and saved.documentVersionId and saved.reviewRunId
    assert saved.requiredArtifacts == REQUIRED_ARTIFACTS
    assert {artifact.type for artifact in saved.artifacts} == {"original"}
    assert snapshot["document"]["filename"] == "脱敏测试.docx"
    assert len(snapshot["versions"]) == 1
    assert len(snapshot["runs"]) == 1
    assert snapshot["facts"][0]["path"] == "case.report_reason"
    assert snapshot["issues"][0]["rule_id"] == "CASE-001"
    assert snapshot["artifacts"][0]["artifact_type"] == "original"


def test_openapi_exposes_complete_review_lifecycle_routes():
    paths = app.openapi()["paths"]

    assert {
        "/api/v1/reviews/{task_id}/versions",
        "/api/v1/reviews/{task_id}/issues/{rule_id}/actions",
        "/api/v1/reviews/{task_id}/issues/{rule_id}/follow-up-answer",
        "/api/v1/reviews/{task_id}/domains/{domain}/retry",
        "/api/v1/reviews/{task_id}/warnings/acknowledge",
        "/api/v1/reviews/{task_id}/artifacts/{artifact_id}",
        "/api/v1/reviews/{task_id}/archive",
    } <= set(paths)
