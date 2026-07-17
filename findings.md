# 实施发现

## Baseline

- Branch: `codex/template-complete-review`
- Base: `2d78f11 feat: optimize police review workflow and diagnostics`
- Remote tracking: `origin/codex/template-complete-review`
- Root checkout has unrelated uncommitted files; all implementation occurs in this isolated worktree.

## Confirmed Input Defect

- The provided DOCX contains readable `word/document.xml` but `word/media/image1.png` has a bad CRC.
- Current `python-docx` loading fails the whole document with `parse_failed`; selective Open XML reading is the required root-cause fix.

## Decisions

- Use the internal template as rule authority.
- Use existing Qwen only for evidence-backed extraction/semantic review.
- Derive completeness and consistency deterministically.
- Keep exact evidence and append-only human actions through archive.

