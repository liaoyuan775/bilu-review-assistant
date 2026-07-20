# Domain-contract-driven extraction design

## Goal

Make all seven Qwen extraction domains use maintainable, field-specific contracts.
Each contract is the single source for:

- the domain-specific prompt fragment;
- the strict JSON Schema sent to Qwen;
- local response validation;
- actionable correction feedback.

All initial requests and retries must continue to use
`response_format.type=json_schema`, `strict=true`, and
`enable_thinking=false`. Plain JSON and Tool Calling fallback remain forbidden.

## File layout

The shared prompt rules and seven domain contracts are stored separately:

```text
backend/
├── domain-contracts/
│   ├── header_procedure.json
│   ├── case_timeline.json
│   ├── contact_channels.json
│   ├── risk_and_evidence.json
│   ├── online_money.json
│   ├── offline_delivery.json
│   └── special_scenarios.json
└── prompt-templates/
    └── domain-extraction.txt
```

The shared template contains only cross-domain instructions: evidence policy,
clarity semantics, prohibition on inference, anchor syntax, and output rules.
Each domain file contains its own boundaries, fact definitions, entity
definitions, and relationships.

## Domain contract format

Each JSON file has this conceptual structure:

```json
{
  "domain": "online_money",
  "title": "线上资金流",
  "include": ["手机银行转账", "扫码支付", "线上返款"],
  "exclude": ["银行取现", "现金交付", "实物交付"],
  "facts": {
    "online_money.used": {
      "description": "是否发生线上资金转出",
      "valueSchema": {
        "type": ["boolean", "null"]
      }
    },
    "online_money.total": {
      "description": "线上转出总额，不含取现和现金交付",
      "valueSchema": {
        "type": ["number", "null"],
        "minimum": 0
      }
    }
  },
  "entities": {
    "transfers": {
      "description": "逐笔线上转账",
      "applicabilityPath": "online_money.used",
      "countPath": "online_money.transfer_count",
      "fields": {
        "amount": {
          "description": "本笔转账金额",
          "valueSchema": {
            "type": ["number", "null"],
            "minimum": 0
          }
        }
      }
    }
  }
}
```

Supported value schemas are deliberately limited to the subset needed by the
project:

- `string|null`;
- `boolean|null`;
- `number|null`;
- `integer|null`;
- `array<string>|null`;
- optional `minimum`, `maximum`, `enum`, `minItems`, and `maxItems`.

Arbitrary JSON Schema fragments are rejected during configuration loading.
This keeps provider compatibility predictable and makes configuration errors
actionable.

## Loading and startup validation

`app/data/domain_contracts.py` loads all files as UTF-8 and validates them
with strict Pydantic configuration models.

Startup fails with the file name and configuration path when any invariant is
violated:

- exactly the seven declared domains must exist;
- file name and `domain` must agree;
- no fact path may occur in more than one domain;
- every fact path referenced by `template_rules.json` must exist exactly once;
- entity names and fields must be unique;
- `applicabilityPath` and `countPath` must reference facts in the same domain;
- rule repeat-entity definitions must agree with the domain contract;
- only the supported value-schema subset is accepted.

The current Python constants for domain facts, entity fields, entity counts,
and entity applicability are replaced by derived read-only values from the
loaded contracts. Domain order is retained as an explicit seven-item tuple so
concurrency and display ordering remain stable.

## Prompt generation

The final prompt is assembled deterministically for every request:

```text
shared prompt template
+ selected domain contract
+ selected batch fields
+ selected entity definitions
+ current document structural text
+ current document question/answer text
+ current document anchor aliases
+ correction feedback when retrying
```

The rendered domain fragment lists, for every requested fact and entity field:

- path;
- Chinese description;
- expected value type and numeric/list bounds;
- domain inclusion and exclusion boundaries;
- entity count and applicability relationships.

The prompt is assembled by application code. No model is used to generate or
rewrite prompts. Given the same contract, document, batch, and correction
feedback, the output is byte-for-byte stable.

## JSON Schema generation

The same selected contract generates the Schema sent in
`response_format.json_schema.schema`.

Facts no longer share one permissive value definition. Reusable definitions
are grouped by exact value constraint, for example:

```text
$defs.booleanOrNullFact
$defs.nonNegativeNumberOrNullFact
$defs.nonNegativeIntegerOrNullFact
$defs.stringOrNullFact
$defs.stringListOrNullFact
```

Each fact path references only its exact definition. Field descriptions remain
in the prompt so the provider-facing Schema stays compact.

The Schema also includes the current document's eligible anchor aliases as an
enum. Blank-answer and guidance-only anchors are excluded.

The clarity/evidence relationship remains enforced locally:

- `clear` and `unclear` require a typed non-null value and one to three
  eligible evidence anchors;
- `missing` and `unknown` require `value=null` and
  `evidenceAnchorIds=[]`.

Provider-compatible Schema keywords are used for model requests. Stronger
semantic checks remain local instead of relying on unsupported conditional
Schema features.

## Response validation

Validation runs in four ordered layers:

1. Parse JSON and verify the strict top-level response shape.
2. Validate the response against the exact generated field-level Schema.
3. Convert it to `CaseExtraction`.
4. Validate evidence, domain boundaries, entity counts, sums, applicability,
   and other business relationships.

The project adds the standard `jsonschema` package for layer 2 rather than
implementing a partial validator manually. Pydantic continues to own
application models and configuration validation.

## Correction behavior

A validation failure records:

- domain;
- batch;
- exact fact or entity field;
- expected type or invariant;
- actual value category;
- corrective instruction from the contract.

The correction request uses the same strict JSON Schema configuration as the
initial request. Correction feedback identifies the exact failed field, but
the response unit is never a single field.

Entity-free domains use fixed fact batches. A failed batch is regenerated in
full while successful batches in the same domain are retained. The regenerated
batch is merged by its declared path set, then the complete domain is validated
again.

Domains containing repeated entities are atomic. Any fact, entity count,
applicability, duplicate ID, entity field, or cross-field failure regenerates
the complete domain because a partial response would not contain enough
context to preserve counts, IDs, sums, and applicability relationships.

The retry units are therefore:

- failed fixed batch for entity-free domains;
- complete domain for domains containing repeated entities;
- never an individual fact or entity field.

Retry limits remain finite and configurable in application configuration.
There is no plain JSON or Tool Calling fallback.

## Demo and upload consistency

Upload and demo review paths continue to call the same extraction pipeline.
Both paths must persist:

- failed domain names;
- domain error codes;
- failed field;
- actionable correction summary;
- successful partial extraction.

The frontend can therefore show the actual failing domain and field instead of
only the aggregate `template_domain_failed` message.

## Migration

Migration is performed domain by domain:

1. Add contract models and loader.
2. Populate all seven contracts from the current rule catalog and Python
   constants.
3. Assert contract coverage against `template_rules.json`.
4. Switch prompt and Schema generation to contracts.
5. Switch local validation and correction feedback to contracts.
6. Remove only the Python constants made redundant by the contracts.

The rule catalog remains the source for review rules. Domain contracts own
model-extraction types and instructions. Startup cross-validation prevents the
two sources from silently diverging.

## Verification

Automated tests cover:

- loading all seven valid contracts;
- clear errors for malformed or incomplete contracts;
- exact rule-path coverage;
- field-specific Schema types and limits;
- prompt descriptions and include/exclude boundaries;
- local rejection of a typed error such as
  `online_money.used.value=36400`;
- clarity/value/evidence combinations;
- complete failed-batch correction and retained successful batches;
- atomic entity-domain correction;
- upload and demo persistence of failed-domain details;
- no plain/tool fallback in source or request payloads;
- configured seven-domain concurrency.

The final integration check uses
`backend/test-fixtures/06-all-statuses-demo.docx` through the frontend proxy
at `127.0.0.1:4173`. It must complete with 34 results, zero failed domains,
and logs showing only `strategy=schema` requests.
