import { useEffect, useMemo } from "react";
import { AlertTriangle, BoxSelect, PanelLeftClose, PanelLeftOpen } from "lucide-react";

import { evidenceAnchorRangesFor, evidenceLocationsFor, isEvidenceParagraph } from "./evidenceSelection";
import type { ParsedDocument, ReviewResult } from "./types";


interface DocumentEvidencePaneProps {
  document: ParsedDocument;
  selectedResult: ReviewResult | null;
  collapsed: boolean;
  onToggle: () => void;
}

export function DocumentEvidencePane({ document, selectedResult, collapsed, onToggle }: DocumentEvidencePaneProps) {
  const anchorRanges = useMemo(
    () => evidenceAnchorRangesFor(selectedResult, document),
    [document, selectedResult],
  );
  const locations = evidenceLocationsFor(selectedResult);
  const selectedIds = new Set(anchorRanges.map((range) => range.blockId));

  useEffect(() => {
    const first = anchorRanges[0];
    if (!first || collapsed) return;
    window.setTimeout(() => {
      documentGlobal().getElementById(`block-${first.blockId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 40);
  }, [anchorRanges, collapsed]);

  return (
    <section className={`document-pane template-evidence-pane ${collapsed ? "collapsed" : ""}`} aria-label="笔录原文证据">
      <div className="pane-header">
        <div>
          <h2>笔录原文</h2>
          <span>{anchorRanges.length > 0 ? `已定位 ${anchorRanges.length} 个证据块` : "选择问题后定位证据"}</span>
        </div>
        <button className="icon-button muted" onClick={onToggle} title={collapsed ? "展开原文" : "收起原文"}>
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>
      {!collapsed && (
        <div className="document-scroll">
          {document.pages.map((page) => (
            <article className="document-page" key={page.page}>
              <div className="page-number">{document.format === "DOCX" ? `逻辑页 ${page.page}` : `第 ${page.page} 页`}</div>
              {page.paragraphs.map((paragraph, index) => {
                const selected = selectedIds.has(paragraph.id)
                  || (selectedIds.size === 0 && isEvidenceParagraph(locations, page.page, index + 1));
                return (
                  <p
                    id={`block-${paragraph.id}`}
                    className={selected ? "evidence-highlight exact-anchor" : ""}
                    key={paragraph.id || `${page.page}-${index}`}
                  >
                    <span className="paragraph-index">{index + 1}</span>
                    <span className="paragraph-text">{paragraph.text}</span>
                    {selected && <BoxSelect className="anchor-indicator" size={14} aria-label="精确证据锚点" />}
                    {paragraph.sourceType !== "native_text" && (
                      <small className={`source-chip ${paragraph.sourceType}`}>
                        {sourceLabel(paragraph.sourceType, paragraph.confidence)}
                      </small>
                    )}
                  </p>
                );
              })}
            </article>
          ))}
          {document.pages.length === 0 && <div className="document-empty"><AlertTriangle size={18} />没有可展示的解析页</div>}
        </div>
      )}
    </section>
  );
}

const documentGlobal = () => window.document;

const sourceLabel = (source: ParsedDocument["pages"][number]["paragraphs"][number]["sourceType"], confidence: number | null) => {
  if (source === "table") return "表格";
  if (source === "header") return "页眉";
  if (source === "footer") return "页脚";
  return `图像识别${confidence === null ? "" : ` ${Math.round(confidence * 100)}%`}`;
};

