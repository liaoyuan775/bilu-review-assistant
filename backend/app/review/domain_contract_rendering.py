import json
from pathlib import Path

from jsonschema import Draft202012Validator

from app.core.errors import AppError
from app.core.models import EvidenceBlock, ParsedDocument
from app.data.domain_contracts import DomainContract, FactContract, ValueSchema


ROOT = Path(__file__).resolve().parent.parent.parent
PROMPT_TEMPLATE = (ROOT / "prompt-templates" / "domain-extraction.txt").read_text(encoding="utf-8")
DOMAIN_PROMPT_ROOT = ROOT / "prompt-templates" / "domains"

CLARITY_DESCRIPTION = (
    "原文明确程度：clear=明确肯定或否定；unclear=回答含糊；"
    "unknown=原文明示无法确认；missing=未提供该事实。"
)
EVIDENCE_ANCHOR_DESCRIPTION = (
    "直接支持该事实的证据锚点；clear 或 unclear 必须提供，"
    "unknown 或 missing 必须为空数组。"
)


def _anchor_aliases(document: ParsedDocument) -> dict[str, str]:
    return {
        paragraph.id: f"A{index:03d}"
        for index, paragraph in enumerate(
            (paragraph for page in document.pages for paragraph in page.paragraphs),
            start=1,
        )
    }


def evidence_anchor_aliases(document: ParsedDocument) -> dict[str, str]:
    """Map unified evidence-block IDs to the short aliases exposed to Qwen."""
    if document.evidenceBlocks:
        return {
            block.id: f"A{index:03d}"
            for index, block in enumerate(document.evidenceBlocks, start=1)
        }
    return _anchor_aliases(document)


def _type_label(value_schema: ValueSchema) -> str:
    label = "|".join(value_schema.type)
    constraints: list[str] = []
    if value_schema.minimum is not None:
        constraints.append(f"minimum={value_schema.minimum:g}")
    if value_schema.maximum is not None:
        constraints.append(f"maximum={value_schema.maximum:g}")
    if value_schema.items is not None:
        constraints.append(f"items={value_schema.items}")
    if value_schema.minItems is not None:
        constraints.append(f"minItems={value_schema.minItems}")
    if value_schema.maxItems is not None:
        constraints.append(f"maxItems={value_schema.maxItems}")
    return f"{label} ({', '.join(constraints)})" if constraints else label


def _render_fact(path: str, fact: FactContract) -> str:
    return f"- {path}: {fact.description}; value 类型={_type_label(fact.valueSchema)}"


def render_domain_prompt(
    document: ParsedDocument,  # 解析后的文档对象
    contract: DomainContract,  # 领域契约对象
    fact_paths: tuple[str, ...] | None = None,  # 事实路径元组，可选参数
    *,
    correction: str | None = None,  # 校正信息，仅关键字参数
) -> str:
    # 如果提供了事实路径则使用，否则使用契约中的所有事实
    selected_paths = fact_paths if fact_paths is not None else tuple(contract.facts)
    # 验证所选事实路径是否都在契约的事实集合中
    if not set(selected_paths).issubset(contract.facts):
        raise ValueError(f"Fact path does not belong to extraction domain: {contract.domain}")

    # 获取证据锚点的别名
    aliases = evidence_anchor_aliases(document)
    if document.evidenceBlocks:
        # 将问答按ID组织成字典
        qa_by_id = {block.id: block for block in document.questionAnswers}
        # 生成问答交换内容
        exchanges = "\n".join(
            f"[问答{index}][锚点:{aliases[block.id]}] {block.text}"
            for index, block in enumerate(document.evidenceBlocks, start=1)
            if block.kind == "qa" and qa_by_id.get(block.id, None) is not None
            and qa_by_id[block.id].answerClarity != "blank"
        )
        # 生成结构化文本内容
        structural = "\n".join(
            f"[锚点:{aliases[block.id]}][第{block.page or 1}页] {block.text}"
            for block in document.evidenceBlocks
            if block.kind == "text"
        )
    else:
        # 收集所有问答锚点ID
        qa_anchor_ids = {
            anchor
            for block in document.questionAnswers
            for anchor in block.anchorIds
        }
        # 生成问答交换内容
        exchanges = "\n".join(
            f"[问答{index}][锚点:{','.join(aliases[anchor] for anchor in block.anchorIds)}] "
            f"问：{block.question} 答：{block.answer}"
            for index, block in enumerate(document.questionAnswers, start=1)
            if block.answerClarity != "blank"
        )
        # 生成结构化文本内容
        structural = "\n".join(
            f"[锚点:{aliases[paragraph.id]}][第{page.page}页] {paragraph.text}"
            for page in document.pages
            for paragraph in page.paragraphs
            if paragraph.id not in qa_anchor_ids
        )

    # 构建请求行列表
    requested_lines = [
        "必须逐项返回这些事实路径：" + json.dumps(selected_paths, ensure_ascii=False),
        "事实：",
    ]
    # 添加每个事实的渲染内容
    requested_lines.extend(_render_fact(path, contract.facts[path]) for path in selected_paths)
    requested_lines.append("实体：")
    # 根据是否有事实路径或实体决定如何处理实体部分
    if fact_paths is not None or not contract.entities:
        requested_lines.append("必须逐项返回这些实体数组及字段：{}")
        requested_lines.append("- 无")
    else:
        requested_lines.append(
            "必须逐项返回这些实体数组及字段："
            + json.dumps(
                {
                    entity_type: list(entity.fields)
                    for entity_type, entity in contract.entities.items()
                },
                ensure_ascii=False,
            )
        )
        # 添加每个实体的描述和元数据
        for entity_type, entity in contract.entities.items():
            metadata = [f"entityType={entity_type}"]
            if entity.applicabilityPath:
                metadata.append(f"适用字段={entity.applicabilityPath}")
            if entity.countPath:
                metadata.append(f"计数字段={entity.countPath}")
            requested_lines.append(f"- {entity.description}; {'; '.join(metadata)}")
            # 添加每个字段的描述和类型信息
            requested_lines.extend(
                f"  - {field}: {definition.description}; value 类型={_type_label(definition.valueSchema)}"
                for field, definition in entity.fields.items()
            )

    # 构建边界信息
    boundary = "\n".join([
        "包含：" + "；".join(contract.include),
        "排除：" + "；".join(contract.exclude),
    ])
    # 创建替换字典
    replacements = {
        "{{DOMAIN_NAME}}": contract.domain,
        "{{DOMAIN_TITLE}}": contract.title,
        "{{DOMAIN_BOUNDARY}}": boundary,
        "{{DOMAIN_INSTRUCTIONS}}": (
            DOMAIN_PROMPT_ROOT / f"{contract.domain.replace('_', '-')}.txt"
        ).read_text(encoding="utf-8").strip(),
        "{{REQUESTED_CONTRACT}}": "\n".join(requested_lines),
        "{{CORRECTION}}": correction or "无，这是首次请求。",
        "{{STRUCTURAL_TEXT}}": structural,
        "{{QUESTION_ANSWERS}}": exchanges,
    }
    # 使用模板和替换值生成提示
    prompt = PROMPT_TEMPLATE
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    return prompt


def _value_schema(schema: ValueSchema) -> dict:
    rendered: dict = {"type": list(schema.type)}
    if schema.minimum is not None:
        rendered["minimum"] = schema.minimum
    if schema.maximum is not None:
        rendered["maximum"] = schema.maximum
    if schema.enum is not None:
        rendered["enum"] = list(schema.enum)
    if schema.items is not None:
        rendered["items"] = {"type": schema.items}
    if schema.minItems is not None:
        rendered["minItems"] = schema.minItems
    if schema.maxItems is not None:
        rendered["maxItems"] = schema.maxItems
    return rendered


def _fact_schema(fact: FactContract, allowed_anchor_ids: tuple[str, ...] | None) -> dict:
    anchor_items = (
        {"$ref": "#/$defs/anchorId"}
        if allowed_anchor_ids is not None
        else {"type": "string"}
    )
    return {
        "type": "object",
        "description": fact.description,
        "properties": {
            "value": {
                **_value_schema(fact.valueSchema),
                "description": fact.description,
            },
            "clarity": {
                "type": "string",
                "enum": ["clear", "unclear", "unknown", "missing"],
                "description": CLARITY_DESCRIPTION,
            },
            "evidenceAnchorIds": {
                "type": "array",
                "description": EVIDENCE_ANCHOR_DESCRIPTION,
                "maxItems": 5,
                "items": anchor_items,
            },
        },
        "required": ["value", "clarity", "evidenceAnchorIds"],
        "additionalProperties": False,
    }


def build_domain_schema(
    contract: DomainContract,
    fact_paths: tuple[str, ...] | None = None,
    allowed_anchor_ids: tuple[str, ...] | None = None,
) -> dict:
    selected_paths = fact_paths if fact_paths is not None else tuple(contract.facts)
    if not set(selected_paths).issubset(contract.facts):
        raise ValueError(f"Fact path does not belong to extraction domain: {contract.domain}")

    entity_properties: dict[str, dict] = {}
    if fact_paths is None:
        for entity_type, entity in contract.entities.items():
            entity_properties[entity_type] = {
                "type": "array",
                "description": entity.description,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "minLength": 1,
                            "description": "当前业务域内唯一的实体编号。",
                        },
                        "entityType": {
                            "type": "string",
                            "const": entity_type,
                            "description": f"实体类型，固定为 {entity_type}。",
                        },
                        "fields": {
                            "type": "object",
                            "description": f"{entity.description}的字段。",
                            "properties": {
                                field: _fact_schema(definition, allowed_anchor_ids)
                                for field, definition in entity.fields.items()
                            },
                            "required": list(entity.fields),
                            "additionalProperties": False,
                        },
                    },
                    "required": ["id", "entityType", "fields"],
                    "additionalProperties": False,
                },
            }

    schema = {
        "type": "object",
        "properties": {
            "facts": {
                "type": "object",
                "properties": {
                    path: _fact_schema(contract.facts[path], allowed_anchor_ids)
                    for path in selected_paths
                },
                "required": list(selected_paths),
                "additionalProperties": False,
            },
            "entities": {
                "type": "object",
                "properties": entity_properties,
                "required": list(entity_properties),
                "additionalProperties": False,
            },
            "failedDomains": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 0,
            },
        },
        "required": ["facts", "entities", "failedDomains"],
        "additionalProperties": False,
    }
    if allowed_anchor_ids is not None:
        schema["$defs"] = {
            "anchorId": {"type": "string", "enum": list(allowed_anchor_ids)},
        }
    return schema


def validate_schema_payload(payload: dict, schema: dict, domain: str) -> None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: [str(part) for part in error.path],
    )
    if not errors:
        return
    error = errors[0]
    field = ".".join(str(part) for part in error.absolute_path)
    raise AppError(
        "invalid_model_schema",
        f"{domain} 域结果不符合字段类型约束。",
        502,
        retry_strategy="schema",
        field=field or "payload",
        correction_hint=error.message,
    )
