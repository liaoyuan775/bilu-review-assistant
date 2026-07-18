from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import QWEN_MODEL  # noqa: E402
from app.data.rules import TEMPLATE_RULE_CATALOG  # noqa: E402
from app.core.models import RuleStatus  # noqa: E402
from app.parsing.parser import parse_document  # noqa: E402
from app.review.extraction import (  # noqa: E402
    DEFAULT_DOMAIN_CONCURRENCY,
    DOMAIN_ENTITY_FIELDS,
    DOMAIN_FACT_PATHS,
    TemplateDomainFailure,
    run_template_review,
)
from app.review.rules import _boolean_value, evaluate_template_rules  # noqa: E402
from app.core.template_models import CaseExtraction, ExtractedEntity, ExtractedFact, TemplateRule  # noqa: E402
from scripts.generate_template_gold_cases import (  # noqa: E402
    _case_extraction,
    build_gold_corpus,
    scan_prohibited_sensitive_shapes,
)


EXPECTED_MODEL = "Qwen3.6-35B-A3B"

GOLD_SEMANTIC_ALIAS_PATHS = {
    "case.initial_channel",
    "case.contact_method",
    "case.initial_contact",
    "case.channel_changes",
    "case.total_loss",
    "case.payment_summary",
    "case.rebate_summary",
    "privacy.disclosure_occurred",
    "privacy.disclosed_information",
    "timeline.incident_at",
    "contact.initial_channel",
}


def _fact(value=None, clarity: str = "clear", anchor: str = "gold-anchor") -> ExtractedFact:
    return ExtractedFact(
        value=value,
        clarity=clarity,
        evidenceAnchorIds=[] if clarity == "missing" else [anchor],
        sourceConfidence=1.0,
    )


def _value(path: str):
    from scripts.generate_template_gold_cases import _value_for
    return _value_for(path)


def _satisfying_value(rule: TemplateRule):
    condition = rule.appliesWhen
    if condition is None:
        return None
    if condition.operator in {"equals", "in"}:
        return condition.value[0] if condition.operator == "in" else condition.value
    if condition.operator == "not_equals":
        return not condition.value if isinstance(condition.value, bool) else "OTHER_TEST_VALUE"
    if condition.operator in {"truthy", "exists"}:
        return True
    return float(condition.value) + (1 if condition.operator == "gt" else 0)


def _contrary_value(rule: TemplateRule):
    condition = rule.appliesWhen
    if condition is None:
        return None
    if condition.operator == "equals":
        return not condition.value if isinstance(condition.value, bool) else "OTHER_TEST_VALUE"
    if condition.operator == "not_equals":
        return condition.value
    if condition.operator in {"truthy", "exists"}:
        return False
    if condition.operator == "in":
        return "OUTSIDE_TEST_VALUE"
    return float(condition.value) - 1


def _covered_extraction(rule: TemplateRule) -> CaseExtraction:
    facts = {path: _fact(_value(path), anchor=f"anchor-{path}") for path in rule.requiredFields}
    if rule.appliesWhen:
        facts[rule.appliesWhen.path] = _fact(
            _satisfying_value(rule), anchor=f"anchor-{rule.appliesWhen.path}"
        )
    entities: dict[str, list[ExtractedEntity]] = {}
    if rule.repeatEntity:
        repeated = rule.repeatEntity
        fields = {
            field: _fact(100 if field in {"amount", "amount_or_value"} else f"ENTITY_TEST_{field}", anchor=f"anchor-{field}")
            for field in repeated.requiredFields
        }
        entities[repeated.entityType] = [
            ExtractedEntity(id=f"{repeated.entityType}-1", entityType=repeated.entityType, fields=fields)
        ]
        if repeated.countPath:
            facts[repeated.countPath] = _fact(1, anchor=f"anchor-{repeated.countPath}")
    for check in rule.consistencyChecks:
        if check.type == "sum_matches":
            entities.setdefault(check.entityType, [ExtractedEntity(
                id=f"{check.entityType}-1",
                entityType=check.entityType,
                fields={check.entityField: _fact(100)},
            )])
            facts[check.totalPath] = _fact(100)
        elif check.type == "rebate_net_loss":
            facts[check.leftPath] = _fact(100)
            facts[check.rightPath] = _fact(10)
            facts[check.resultPath] = _fact(90)
        elif check.type == "chronology":
            facts[check.earlierPath] = _fact("2026-07-01T09:00:00")
            facts[check.laterPath] = _fact("2026-07-01T10:00:00")
        elif check.type == "count_matches":
            entities.setdefault(check.entityType, [ExtractedEntity(
                id=f"{check.entityType}-1",
                entityType=check.entityType,
                fields={},
            )])
            facts[check.countPath] = _fact(len(entities[check.entityType]))
    return CaseExtraction(facts=facts, entities=entities)


def _mutation_extraction(rule: TemplateRule, kind: str) -> CaseExtraction:
    extraction = _covered_extraction(rule)
    if kind == "covered":
        return extraction
    if kind == "missing":
        for path in rule.requiredFields:
            extraction.facts[path] = _fact(clarity="missing")
        return extraction
    target = rule.requiredFields[0]
    if kind == "incomplete" or not rule.consistencyChecks:
        extraction.facts[target] = _fact(None, "unknown", f"anchor-{target}")
        return extraction
    check = rule.consistencyChecks[0]
    if check.type == "sum_matches":
        extraction.facts[check.totalPath] = _fact(999)
    elif check.type == "rebate_net_loss":
        extraction.facts[check.resultPath] = _fact(999)
    elif check.type == "chronology":
        extraction.facts[check.earlierPath] = _fact("2026-07-01T11:00:00")
        extraction.facts[check.laterPath] = _fact("2026-07-01T10:00:00")
    elif check.type == "count_matches":
        extraction.facts[check.countPath] = _fact(2)
    return extraction


def _percentage(passed: int, total: int) -> float:
    return round(100.0 * passed / total, 2) if total else 100.0


def _gold_semantic_projection(
    extraction: CaseExtraction,
    issues,
    expected: CaseExtraction,
) -> dict:
    facts = {}
    for path, expected_fact in sorted(expected.facts.items()):
        fact = extraction.facts.get(path)
        if fact is None:
            facts[path] = None
        elif path in GOLD_SEMANTIC_ALIAS_PATHS:
            facts[path] = {"clarity": fact.clarity}
        else:
            value = (
                expected_fact.value
                if _values_equal(fact.value, expected_fact.value)
                else fact.value
            )
            facts[path] = {"value": value, "clarity": fact.clarity}
    entities = {}
    for entity_type, items in sorted(extraction.entities.items()):
        expected_items = expected.entities.get(entity_type, [])
        normalized = [
            {
                field: {
                    "value": (
                        expected_items[index].fields[field].value
                        if index < len(expected_items)
                        and field in expected_items[index].fields
                        and _values_equal(fact.value, expected_items[index].fields[field].value)
                        else fact.value
                    ),
                    "clarity": fact.clarity,
                }
                for field, fact in sorted(item.fields.items())
            }
            for index, item in enumerate(items)
        ]
        entities[entity_type] = sorted(
            normalized,
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=str),
        )
    issue_projection = {
        issue.ruleId: {
            "status": issue.status.value,
            "missingFields": sorted(issue.missingFields),
        }
        for issue in sorted(issues, key=lambda item: item.ruleId)
    }
    return {"facts": facts, "entities": entities, "issues": issue_projection}


def _gold_semantic_fingerprint(
    extraction: CaseExtraction,
    issues,
    expected: CaseExtraction,
) -> str:
    payload = _gold_semantic_projection(extraction, issues, expected)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _semantic_drift_paths(baseline: dict, candidate: dict) -> list[str]:
    paths: set[str] = set()
    for section in ("facts", "entities", "issues"):
        before = baseline.get(section, {})
        after = candidate.get(section, {})
        for key in set(before).union(after):
            if before.get(key) != after.get(key):
                paths.add(f"{section}.{key}")
    return sorted(paths)


def _values_equal(actual, expected) -> bool:
    if isinstance(expected, bool):
        return _boolean_value(actual) is expected
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            return Decimal(str(actual)) == Decimal(str(expected))
        except (InvalidOperation, TypeError, ValueError):
            if isinstance(actual, str):
                numbers = re.findall(r"(?<!\d)-?\d+(?:\.\d+)?(?!\d)", actual)
                return len(numbers) == 1 and Decimal(numbers[0]) == Decimal(str(expected))
            return False
    if isinstance(expected, str) and expected.startswith(("VALUE_TEST_", "ENTITY_TEST_")):
        return isinstance(actual, str) and expected in actual
    return actual == expected


def _gold_accuracy(
    extraction: CaseExtraction,
    expected: CaseExtraction,
) -> tuple[int, int, list[dict[str, str]]]:
    passed = total = 0
    mismatches: list[dict[str, str]] = []
    all_fact_paths = sorted({path for paths in DOMAIN_FACT_PATHS.values() for path in paths})
    for path in all_fact_paths:
        total += 1
        actual_fact = extraction.facts.get(path)
        expected_fact = expected.facts.get(path)
        if expected_fact is None:
            matches = actual_fact is None or actual_fact.clarity == "missing"
        else:
            matches = (
                actual_fact is not None
                and actual_fact.clarity == expected_fact.clarity
                and (
                    path in GOLD_SEMANTIC_ALIAS_PATHS
                    or _values_equal(actual_fact.value, expected_fact.value)
                )
            )
        passed += matches
        if not matches:
            mismatches.append({
                "kind": "fact",
                "path": path,
                "expectedClarity": expected_fact.clarity if expected_fact else "missing",
                "actualClarity": actual_fact.clarity if actual_fact else "absent",
                "valueMatch": str(
                    actual_fact is not None
                    and expected_fact is not None
                    and (
                        path in GOLD_SEMANTIC_ALIAS_PATHS
                        or _values_equal(actual_fact.value, expected_fact.value)
                    )
                ).lower(),
            })

    entity_types = sorted({
        entity_type
        for fields in DOMAIN_ENTITY_FIELDS.values()
        for entity_type in fields
    })
    for entity_type in entity_types:
        actual_items = extraction.entities.get(entity_type, [])
        expected_items = expected.entities.get(entity_type, [])
        total += 1
        count_matches = len(actual_items) == len(expected_items)
        passed += count_matches
        if not count_matches:
            mismatches.append({
                "kind": "entity_count",
                "path": entity_type,
                "expectedCount": str(len(expected_items)),
                "actualCount": str(len(actual_items)),
            })
        for index, expected_item in enumerate(expected_items):
            actual_item = actual_items[index] if index < len(actual_items) else None
            for field, expected_fact in sorted(expected_item.fields.items()):
                total += 1
                actual_fact = actual_item.fields.get(field) if actual_item is not None else None
                matches = (
                    actual_fact is not None
                    and actual_fact.clarity == expected_fact.clarity
                    and _values_equal(actual_fact.value, expected_fact.value)
                )
                passed += matches
                if not matches:
                    mismatches.append({
                        "kind": "entity_field",
                        "path": f"{entity_type}[{index}].{field}",
                        "expectedClarity": expected_fact.clarity,
                        "actualClarity": actual_fact.clarity if actual_fact else "absent",
                        "valueMatch": str(
                            actual_fact is not None
                            and _values_equal(actual_fact.value, expected_fact.value)
                        ).lower(),
                    })
    return passed, total, mismatches


def _natural_expected_extraction(case: dict) -> CaseExtraction:
    facts = {
        path: _fact(spec.get("value"), spec["clarity"], anchor=f"natural-{path}")
        for path, spec in case.get("expectedFacts", {}).items()
    }
    entities = {
        entity_type: [
            ExtractedEntity(
                id=f"natural-{entity_type}-{index + 1}",
                entityType=entity_type,
                fields={
                    field: _fact(spec.get("value"), spec["clarity"], anchor=f"natural-{entity_type}-{index + 1}-{field}")
                    for field, spec in fields.items()
                },
            )
            for index, fields in enumerate(items)
        ]
        for entity_type, items in case.get("expectedEntities", {}).items()
    }
    return CaseExtraction(facts=facts, entities=entities)


def _focused_accuracy(
    extraction: CaseExtraction,
    expected: CaseExtraction,
) -> tuple[int, int, list[dict[str, str]]]:
    passed = total = 0
    mismatches: list[dict[str, str]] = []
    for path, expected_fact in sorted(expected.facts.items()):
        total += 1
        actual_fact = extraction.facts.get(path)
        matches = (
            actual_fact is not None
            and actual_fact.clarity == expected_fact.clarity
            and (
                expected_fact.clarity in {"unknown", "unclear"}
                or _values_equal(actual_fact.value, expected_fact.value)
            )
        )
        passed += matches
        if not matches:
            mismatches.append({
                "kind": "fact",
                "path": path,
                "expectedClarity": expected_fact.clarity,
                "actualClarity": actual_fact.clarity if actual_fact else "absent",
                "valueMatch": str(
                    actual_fact is not None
                    and (
                        expected_fact.clarity in {"unknown", "unclear"}
                        or _values_equal(actual_fact.value, expected_fact.value)
                    )
                ).lower(),
            })
    for entity_type, expected_items in sorted(expected.entities.items()):
        actual_items = extraction.entities.get(entity_type, [])
        total += 1
        count_matches = len(actual_items) == len(expected_items)
        passed += count_matches
        if not count_matches:
            mismatches.append({
                "kind": "entity_count",
                "path": entity_type,
                "expectedCount": str(len(expected_items)),
                "actualCount": str(len(actual_items)),
            })
        for index, expected_item in enumerate(expected_items):
            actual_item = actual_items[index] if index < len(actual_items) else None
            for field, expected_fact in sorted(expected_item.fields.items()):
                total += 1
                actual_fact = actual_item.fields.get(field) if actual_item else None
                matches = (
                    actual_fact is not None
                    and actual_fact.clarity == expected_fact.clarity
                    and _values_equal(actual_fact.value, expected_fact.value)
                )
                passed += matches
                if not matches:
                    mismatches.append({
                        "kind": "entity_field",
                        "path": f"{entity_type}[{index}].{field}",
                        "expectedClarity": expected_fact.clarity,
                        "actualClarity": actual_fact.clarity if actual_fact else "absent",
                        "valueMatch": str(
                            actual_fact is not None
                            and _values_equal(actual_fact.value, expected_fact.value)
                        ).lower(),
                    })
    return passed, total, mismatches


def _focused_semantic_projection(
    extraction: CaseExtraction,
    issues,
    expected: CaseExtraction,
    expected_statuses: dict[str, str],
) -> dict:
    projection = _gold_semantic_projection(extraction, issues, expected)
    projection["entities"] = {
        entity_type: projection["entities"].get(entity_type, [])
        for entity_type in expected.entities
    }
    projection["issues"] = {
        rule_id: projection["issues"].get(rule_id)
        for rule_id in expected_statuses
    }
    return projection


async def _parse_cases(corpus: dict, root: Path):
    outcomes = []
    for case in [*corpus["cases"], *corpus.get("naturalCases", [])]:
        for key in ("docx", "pdf"):
            path = root / case[key]
            parsed = await parse_document(path.name, path.read_bytes())
            outcomes.append((case, key, parsed))
    return outcomes


def evaluate_offline_quality(corpus: dict, root: Path) -> dict:
    parsed = asyncio.run(_parse_cases(corpus, root))
    parse_pass = sum(item.pageCount >= 1 and bool(item.text.strip()) for _, _, item in parsed)
    qa_pass = sum(len(item.questionAnswers) >= case["questionCount"] for case, _, item in parsed)

    rules = {rule.ruleId: rule for rule in TEMPLATE_RULE_CATALOG.rules}
    issue_pass = field_pass = anchor_pass = entity_pass = 0
    for mutation in corpus["mutations"]:
        rule = rules[mutation["ruleId"]]
        extraction = _mutation_extraction(rule, mutation["kind"])
        issue = evaluate_template_rules(extraction, [rule])[0]
        expected = RuleStatus(mutation["expectedStatus"])
        issue_pass += issue.status == expected
        field_pass += (
            issue.status == RuleStatus.COVERED
            or issue.status == RuleStatus.INCONSISTENT
            or bool(issue.missingFields)
        )
        anchor_pass += issue.status == RuleStatus.MISSING or bool(issue.anchorIds)
        entity_pass += rule.repeatEntity is None or bool(extraction.entities.get(rule.repeatEntity.entityType))

    conditional = [rule for rule in rules.values() if rule.appliesWhen]
    applicability_pass = false_positive_pass = 0
    for rule in conditional:
        extraction = _covered_extraction(rule)
        extraction.facts[rule.appliesWhen.path] = _fact(_contrary_value(rule))
        issue = evaluate_template_rules(extraction, [rule])[0]
        applicability_pass += issue.status == RuleStatus.NOT_APPLICABLE
        false_positive_pass += not issue.missingFields and not issue.suggestedQuestion

    first = [
        evaluate_template_rules(_mutation_extraction(rule, "covered"), [rule])[0].model_dump_json()
        for rule in rules.values()
    ]
    second = [
        evaluate_template_rules(_mutation_extraction(rule, "covered"), [rule])[0].model_dump_json()
        for rule in rules.values()
    ]
    scanned = [
        root / case[key]
        for case in [*corpus["cases"], *corpus.get("naturalCases", [])]
        for key in ("docx", "pdf")
    ]
    findings = scan_prohibited_sensitive_shapes(scanned)
    mutation_total = len(corpus["mutations"])
    metrics = {
        "parse": _percentage(parse_pass, len(parsed)),
        "questionAnswer": _percentage(qa_pass, len(parsed)),
        "field": _percentage(field_pass, mutation_total),
        "entity": _percentage(entity_pass, mutation_total),
        "anchor": _percentage(anchor_pass, mutation_total),
        "applicability": _percentage(applicability_pass, len(conditional)),
        "issue": _percentage(issue_pass, mutation_total),
        "falsePositive": _percentage(false_positive_pass, len(conditional)),
        "stability": 100.0 if first == second else 0.0,
        "sensitive": 100.0 if not findings else 0.0,
    }
    return {
        "mode": "offline",
        "caseCount": len(parsed),
        "contractDocumentCount": len(corpus["cases"]) * 2,
        "naturalDocumentCount": len(corpus.get("naturalCases", [])) * 2,
        "ruleCount": len(rules),
        "metrics": metrics,
        "sensitiveFindings": findings,
    }


async def _evaluate_live(
    corpus: dict,
    root: Path,
    runs: int,
    case_limit: int | None = None,
    case_id: str | None = None,
    case_start: int = 1,
    max_concurrency: int = DEFAULT_DOMAIN_CONCURRENCY,
) -> dict:
    if QWEN_MODEL != EXPECTED_MODEL:
        raise RuntimeError(f"Configured model must be {EXPECTED_MODEL}; got {QWEN_MODEL or 'unconfigured'}")
    if case_id:
        selected_cases = [case for case in corpus["cases"] if case["id"] == case_id]
        selected_natural = [case for case in corpus.get("naturalCases", []) if case["id"] == case_id]
    else:
        selected_cases = (
            corpus["cases"][case_start - 1:][:case_limit]
            if case_limit
            else corpus["cases"][case_start - 1:]
        )
        selected_natural = (
            corpus.get("naturalCases", [])
            if case_limit is None and case_start == 1
            else []
        )
    if not selected_cases and not selected_natural:
        raise RuntimeError(f"Unknown gold case: {case_id}")
    documents = []
    for case in selected_cases:
        path = root / case["docx"]
        documents.append({
            "case": case,
            "format": "docx",
            "suite": "contract",
            "document": await parse_document(path.name, path.read_bytes()),
            "expected": _case_extraction(tuple(case["domains"])),
        })
    for case in selected_natural:
        for file_format in ("docx", "pdf"):
            path = root / case[file_format]
            documents.append({
                "case": case,
                "format": file_format,
                "suite": "natural",
                "document": await parse_document(path.name, path.read_bytes()),
                "expected": _natural_expected_extraction(case),
            })
    fingerprints: list[list[tuple[str, str]]] = []
    projections: list[dict[str, dict]] = []
    mismatches: list[dict[str, str]] = []
    recall_pass = recall_total = anchor_pass = applicability_pass = issue_pass = 0
    rule_total = sum(len(item["case"]["expectedRuleStatuses"]) for item in documents) * runs
    document_semaphore = asyncio.Semaphore(1)

    async def evaluate_document(item):
        async with document_semaphore:
            try:
                outcome = await run_template_review(
                    item["document"],
                    group_timings={},
                    max_concurrency=max_concurrency,
                )
            except TemplateDomainFailure as error:
                raise RuntimeError(
                    f"{item['case']['id']}:{item['format']} failed domains: "
                    + json.dumps({
                        "codes": error.domain_errors,
                        "details": error.domain_error_details,
                    }, ensure_ascii=False, sort_keys=True)
                ) from error
            return item, outcome

    for _ in range(runs):
        run_fingerprint = []
        run_projections = {}
        evaluated = await asyncio.gather(*(evaluate_document(item) for item in documents))
        for item, outcome in evaluated:
            case = item["case"]
            expected_extraction = item["expected"]
            expected = case["expectedRuleStatuses"]
            results = {result.ruleId: result for result in outcome.results}
            for rule_id, target in expected.items():
                result = results.get(rule_id)
                actual = result.status.value if result is not None else "absent"
                if actual != target:
                    mismatches.append({
                        "run": str(len(fingerprints) + 1),
                        "caseId": case["id"],
                        "format": item["format"],
                        "ruleId": rule_id,
                        "expected": target,
                        "actual": actual,
                        "missingFields": ",".join(result.missingFacts) if result else "",
                    })
                issue_pass += actual == target
                applicability_pass += actual == target
                anchor_pass += (
                    target in {RuleStatus.MISSING.value, RuleStatus.NEEDS_MANUAL_REVIEW.value}
                    or bool(result and result.evidenceAnchorIds)
                )
            accuracy_pass, accuracy_total, accuracy_mismatches = (
                _gold_accuracy(outcome.extraction, expected_extraction)
                if item["suite"] == "contract"
                else _focused_accuracy(outcome.extraction, expected_extraction)
            )
            recall_pass += accuracy_pass
            recall_total += accuracy_total
            mismatches.extend({
                "run": str(len(fingerprints) + 1),
                "caseId": case["id"],
                "format": item["format"],
                **mismatch,
            } for mismatch in accuracy_mismatches)
            projection = (
                _gold_semantic_projection(outcome.extraction, outcome.issues, expected_extraction)
                if item["suite"] == "contract"
                else _focused_semantic_projection(
                    outcome.extraction,
                    outcome.issues,
                    expected_extraction,
                    expected,
                )
            )
            run_fingerprint.append((
                case["id"],
                item["format"],
                sha256(json.dumps(
                    projection,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")).hexdigest(),
            ))
            run_projections[f"{case['id']}:{item['format']}"] = projection
        fingerprints.append(run_fingerprint)
        projections.append(run_projections)
    scanned = [
        root / case[key]
        for case in [*corpus["cases"], *corpus.get("naturalCases", [])]
        for key in ("docx", "pdf")
    ]
    findings = scan_prohibited_sensitive_shapes(scanned)
    metrics = {
        "requiredRecall": _percentage(recall_pass, recall_total),
        "anchor": _percentage(anchor_pass, rule_total),
        "applicability": _percentage(applicability_pass, rule_total),
        "issue": _percentage(issue_pass, rule_total),
        "semanticStability": 100.0 if all(item == fingerprints[0] for item in fingerprints[1:]) else 0.0,
        "sensitive": 100.0 if not findings else 0.0,
    }
    drift_paths: set[str] = set()
    for candidate in projections[1:]:
        for item in documents:
            case_key = f"{item['case']['id']}:{item['format']}"
            drift_paths.update(_semantic_drift_paths(
                projections[0][case_key],
                candidate[case_key],
            ))
    return {
        "mode": "live",
        "model": QWEN_MODEL,
        "domainConcurrency": max_concurrency,
        "runs": runs,
        "caseCount": len(documents),
        "contractCaseCount": sum(item["suite"] == "contract" for item in documents),
        "naturalDocumentCount": sum(item["suite"] == "natural" for item in documents),
        "ruleCount": len(TEMPLATE_RULE_CATALOG.rules),
        "metrics": metrics,
        "mismatches": mismatches,
        "semanticDriftPaths": sorted(drift_paths),
        "sensitiveFindings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify template-review gold quality.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--case-limit", type=int)
    parser.add_argument("--case-id")
    parser.add_argument("--case-start", type=int, default=1)
    parser.add_argument(
        "--domain-concurrency",
        type=int,
        default=DEFAULT_DOMAIN_CONCURRENCY,
        choices=range(1, 8),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="bilu-template-quality-") as directory:
        root = Path(directory)
        corpus = build_gold_corpus(root)
        report = (
            evaluate_offline_quality(corpus, root)
            if args.offline
            else asyncio.run(_evaluate_live(
                corpus,
                root,
                args.runs,
                args.case_limit,
                args.case_id,
                args.case_start,
                args.domain_concurrency,
            ))
        )
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if all(value == 100.0 for value in report["metrics"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
