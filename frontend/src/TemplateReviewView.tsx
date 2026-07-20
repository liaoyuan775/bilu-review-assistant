import { useMemo, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Archive,
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleSlash2,
  Clock3,
  FileText,
  FileDown,
  ListChecks,
  RefreshCw,
  Search,
  ShieldAlert,
  TriangleAlert,
} from "lucide-react";

import { artifactDownloadUrl } from "./api";
import { DocumentEvidencePane } from "./DocumentEvidencePane";
import { FollowUpPanel } from "./FollowUpPanel";
import {
  displayDomainLabel,
  displayEntityTypeLabel,
  displayFactLabel,
  displayGroupLabel,
  displayReviewReason,
} from "./ruleLabels";
import { VictimProfileCard } from "./VictimProfileCard";
import {
  isManualDecisionClosed,
  manualDecisionLabel,
  reviewActionPolicy,
} from "./reviewActionPolicy";
import {
  actionableStatuses,
  archiveBlockers,
  countTemplateStatuses,
  nextActionableIssueId,
  processingLabel,
  sectionTemplateResults,
  summaryStatuses,
} from "./templateReviewState";
import type { ManualStatus, ReviewResult, ReviewTask, RuleStatus } from "./types";


const statusMeta: Record<RuleStatus, { label: string; className: string; icon: typeof CheckCircle2 }> = {
  covered: { label: "已通过", className: "covered", icon: CheckCircle2 },
  missing: { label: "未询问", className: "missing", icon: AlertCircle },
  incomplete: { label: "回答不清", className: "incomplete", icon: Clock3 },
  inconsistent: { label: "事实矛盾", className: "inconsistent", icon: TriangleAlert },
  not_applicable: { label: "规则不适用", className: "not-applicable", icon: CircleSlash2 },
  needs_manual_review: { label: "待人工判断", className: "manual-review", icon: ShieldAlert },
};

const sectionLabels = {
  open: "待处理问题",
  closed: "已闭环问题",
  not_applicable: "规则不适用",
  covered: "已通过项目",
};

const severityLabels: Record<ReviewResult["severity"], string> = {
  high: "高风险",
  medium: "中风险",
  low: "低风险",
};

interface TemplateReviewViewProps {
  task: ReviewTask;
  selectedRuleId: string | null;
  onSelectRule: (ruleId: string | null) => void;
  onBack: () => void;
  onAction: (ruleId: string, status: ManualStatus, reason?: string) => Promise<boolean>;
  onFollowUp: (ruleId: string, question: string, answer: string) => Promise<void>;
  onGenerateArtifacts: () => Promise<void>;
  onDemoPassAll: () => Promise<void>;
  onArchive: () => Promise<void>;
  onShowReport: () => void;
  onAcknowledgeWarnings: (codes: string[]) => Promise<void>;
  onRetryDomain: (domain: string) => Promise<void>;
  notify: (message: string) => void;
}

export function TemplateReviewView(props: TemplateReviewViewProps) {
  const {
    task,
    selectedRuleId,
    onSelectRule,
    onBack,
    onAction,
    onFollowUp,
    onGenerateArtifacts,
    onDemoPassAll,
    onArchive,
    onShowReport,
    onAcknowledgeWarnings,
    onRetryDomain,
    notify,
  } = props;
  const [filter, setFilter] = useState<"all" | "actionable" | RuleStatus>("all");
  const [search, setSearch] = useState("");
  const [documentCollapsed, setDocumentCollapsed] = useState(false);
  const [followUpRuleId, setFollowUpRuleId] = useState<string | null>(null);
  const [decisionReason, setDecisionReason] = useState("");
  const [generatingArtifacts, setGeneratingArtifacts] = useState(false);
  const [demoPassing, setDemoPassing] = useState(false);
  const selected = task.results.find((item) => item.ruleId === selectedRuleId) ?? null;
  const followUpItem = task.results.find((item) => item.ruleId === followUpRuleId) ?? null;
  const counts = countTemplateStatuses(task.results);
  const blockers = archiveBlockers(task);
  const unresolvedWarnings = task.document?.warnings.filter(
    (warning) => !task.acknowledgedWarnings.includes(warning.code),
  ) ?? [];
  const visible = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return task.results.filter((item) => {
      const matchesFilter = filter === "all"
        || (filter === "actionable" ? actionableStatuses.has(item.status) : item.status === filter);
      const matchesSearch = !keyword
        || `${item.ruleId}${item.ruleName}${item.group}${item.reason}${item.missingFacts.join("")}`.toLowerCase().includes(keyword);
      return matchesFilter && matchesSearch;
    });
  }, [filter, search, task.results]);
  const sections = sectionTemplateResults(visible);
  const readOnly = task.reviewStatus === "archived";
  const missingArtifacts = blockers.some((blocker) => blocker.code === "missing_artifacts");
  const entities = readEntities(task.extractionPayload);

  const act = async (item: ReviewResult, status: ManualStatus) => {
    const requiresReason = status === "ignored" || status === "not_applicable" || status === "resolved";
    if (requiresReason && !decisionReason.trim()) {
      notify("请填写处理依据");
      return;
    }
    if (await onAction(item.ruleId, status, decisionReason.trim())) {
      setDecisionReason("");
      const next = nextActionableIssueId(task.results, item.ruleId);
      if (next) onSelectRule(next);
    }
  };

  return (
    <section className="template-review-page">
      <header className="template-review-header entrance-1">
        <button className="icon-button" onClick={onBack} title="返回新建审查"><ArrowLeft size={19} /></button>
        <FileText size={20} />
        <div className="template-file-heading">
          <h1>{task.document?.name ?? "审查任务"}</h1>
          <p>模板规则 {task.results.length} 项 · 文档版本 {task.documentVersionId?.slice(0, 8) ?? "-"}</p>
        </div>
        <div className="template-header-actions">
          {Boolean(task.demoId) && !readOnly && (
            <button
              className="artifact-link demo-pass-all"
              disabled={demoPassing || task.failedDomains.length > 0 || !task.results.some((item) => actionableStatuses.has(item.status) && !isManualDecisionClosed(item))}
              onClick={async () => {
                setDemoPassing(true);
                try {
                  await onDemoPassAll();
                } finally {
                  setDemoPassing(false);
                }
              }}
            >
              <Check size={15} />{demoPassing ? "正在处理" : "一键测试通过"}
            </button>
          )}
          {!readOnly && missingArtifacts && (
            <button
              className="artifact-link artifact-generate"
              disabled={generatingArtifacts}
              onClick={async () => {
                setGeneratingArtifacts(true);
                try {
                  await onGenerateArtifacts();
                } finally {
                  setGeneratingArtifacts(false);
                }
              }}
            >
              <FileDown size={15} />{generatingArtifacts ? "正在生成" : "生成归档产物"}
            </button>
          )}
          {task.artifacts.map((artifact) => (
            <a key={artifact.id} className="artifact-link" href={artifactDownloadUrl(task.id, artifact.id)}>{artifactLabel(artifact.type)}</a>
          ))}
          {readOnly ? (
            <button className="primary-button compact" onClick={onShowReport}>查看审查报告</button>
          ) : (
            <button className="primary-button compact" disabled={blockers.length > 0} onClick={onArchive}>
              <Archive size={16} />归档
            </button>
          )}
        </div>
      </header>

      {(task.failedDomains.length > 0 || unresolvedWarnings.length > 0) && (
        <div className="review-alert-band">
          {task.failedDomains.map((domain) => (
            <div key={domain}><AlertTriangle size={16} /><span>抽取失败：{displayDomainLabel(domain)}</span><button onClick={() => onRetryDomain(domain)}><RefreshCw size={14} />重试</button></div>
          ))}
          {unresolvedWarnings.length > 0 && (
            <div><AlertTriangle size={16} /><span>{unresolvedWarnings.length} 条解析告警待确认</span><button onClick={() => onAcknowledgeWarnings(unresolvedWarnings.map((item) => item.code))}><Check size={14} />确认</button></div>
          )}
        </div>
      )}

      <div className="template-metrics entrance-2">
        {summaryStatuses.map((status) => {
          const meta = statusMeta[status];
          const Icon = meta.icon;
          return <button key={status} className={filter === status ? "selected" : ""} onClick={() => setFilter(filter === status ? "all" : status)}>
            <Icon size={17} className={meta.className} /><strong>{counts[status]}</strong><span>{meta.label}</span>
          </button>;
        })}
        {task.victimProfile && <VictimProfileCard profile={task.victimProfile} />}
        <div className="archive-gates">
          {task.reviewStatus === "archived" ? <span className="gate-ready"><CheckCircle2 size={16} />已归档只读</span> : blockers.length === 0 ? (
            <span className="gate-ready"><CheckCircle2 size={16} />归档条件已满足</span>
          ) : blockers.map((blocker) => <span key={blocker.code}><AlertCircle size={14} />{blocker.label} {blocker.count}</span>)}
        </div>
      </div>

      {entities.length > 0 && (
        <section className="entity-strip" aria-label="重复明细">
          <strong>重复明细</strong>
          {entities.map((entity) => <span key={entity.type}>{displayEntityTypeLabel(entity.type)}<b>{entity.count}</b></span>)}
        </section>
      )}

      <div className={`template-workspace entrance-3 ${documentCollapsed ? "document-collapsed" : ""}`}>
        {task.document && (
          <DocumentEvidencePane
            document={task.document}
            selectedResult={selected}
            collapsed={documentCollapsed}
            onToggle={() => setDocumentCollapsed((value) => !value)}
          />
        )}
        <section className="template-issues-pane" aria-label="模板审查问题">
          <div className="template-tools">
            <div className="search-box"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索问题、字段或说明" /></div>
            <div className="filter-control">
              <button className={filter === "actionable" ? "active" : ""} onClick={() => setFilter("actionable")}>待处理</button>
              <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>全部</button>
            </div>
          </div>
          <div className="template-group-list">
            {sections.map((section) => (
              <section className={`template-result-section section-${section.key}`} key={section.key}>
                <header className="template-section-heading"><strong>{sectionLabels[section.key]}</strong><span>{section.groups.reduce((total, group) => total + group.results.length, 0)} 项</span></header>
                {section.groups.map((group) => (
                  <section className="template-group" key={`${section.key}-${group.name}`}>
                    <header><span>{group.name}</span><strong>{displayGroupLabel(group.name)}</strong><em>{group.results.length}</em></header>
                    {group.results.map((item) => {
                  const meta = statusMeta[item.status];
                  const Icon = meta.icon;
                  const expanded = item.ruleId === selectedRuleId;
                  const actionPolicy = reviewActionPolicy(item.status);
                  const decisionClosed = isManualDecisionClosed(item);
                  const itemProcessingLabel = processingLabel(item);
                  return <article className={`template-issue section-${section.key} severity-${item.severity} manual-${item.manualDecision.status} ${expanded ? "selected" : ""}`} key={item.ruleId}>
                    <button className="template-issue-summary" onClick={() => onSelectRule(expanded ? null : item.ruleId)}>
                      <Icon size={17} className={meta.className} />
                      <span><code>{item.ruleId}</code><strong>{item.ruleName}</strong></span>
                      {actionableStatuses.has(item.status) && <em className={`risk-badge severity-${item.severity}`}>{severityLabels[item.severity]}</em>}
                      <small className={meta.className}>{meta.label}</small>
                      {itemProcessingLabel && <small className={`processing-label manual-${item.manualDecision.status}`}>{itemProcessingLabel}</small>}
                      {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    </button>
                    {expanded && (
                      <div className="template-issue-detail">
                        <p>{displayReviewReason(item.reason)}</p>
                        {item.missingFacts.length > 0 && <div className="missing-fields">{item.missingFacts.map((field) => <span key={field}>{displayFactLabel(field)}</span>)}</div>}
                        <div className="evidence-quote"><strong>证据原文</strong><p>{item.evidence}</p></div>
                        {item.suggestedQuestion && <div className="suggested-question"><strong>建议补问</strong><p>{item.suggestedQuestion}</p></div>}
                        {actionPolicy && <div className="recommended-action"><strong>推荐处理</strong><p>{actionPolicy.recommendation}</p></div>}
                        {actionPolicy && (
                          <div className={`manual-decision-state ${decisionClosed ? "closed" : "open"}`}>
                            <span>人工处置</span>
                            <strong>{manualDecisionLabel(item)}</strong>
                            {item.manualDecision.reason && <p>记录：{item.manualDecision.reason}</p>}
                          </div>
                        )}
                        {!readOnly && actionPolicy && (
                          <div className="issue-actions">
                            <textarea value={decisionReason} onChange={(event) => setDecisionReason(event.target.value)} placeholder="选择接受现有材料、不适用或不处理时，必须填写处理依据" />
                            <div className="issue-action-buttons">
                              <button className="primary-review-action" onClick={async () => {
                                if (await onAction(item.ruleId, actionPolicy.primary.status, item.suggestedQuestion)) setFollowUpRuleId(item.ruleId);
                              }}><ListChecks size={14} />{actionPolicy.primary.label}</button>
                              {actionPolicy.secondary.map((action) => (
                                <button key={action.status} onClick={() => act(item, action.status)}>
                                  {action.status === "not_applicable" ? <CircleSlash2 size={14} /> : action.status === "resolved" ? <Check size={14} /> : null}
                                  {action.label}
                                </button>
                              ))}
                              {Boolean(task.demoId) && !decisionClosed && (
                                <button className="demo-pass-item" onClick={() => onAction(item.ruleId, "resolved", "脱敏演示：测试通过")}>
                                  <Check size={14} />测试通过
                                </button>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </article>;
                    })}
                  </section>
                ))}
              </section>
            ))}
            {sections.length === 0 && <div className="empty-results"><Search size={22} />没有符合条件的审查项</div>}
          </div>
        </section>
      </div>

      <FollowUpPanel
        item={followUpItem}
        open={Boolean(followUpRuleId)}
        readOnly={readOnly}
        onClose={() => setFollowUpRuleId(null)}
        onSubmit={onFollowUp}
      />
    </section>
  );
}

const readEntities = (payload: ReviewTask["extractionPayload"]) => {
  const entities = payload && typeof payload === "object" ? payload.entities : null;
  if (!entities || typeof entities !== "object" || Array.isArray(entities)) return [];
  return Object.entries(entities).flatMap(([type, value]) =>
    Array.isArray(value) && value.length > 0 ? [{ type, count: value.length }] : [],
  );
};

const artifactLabel = (type: string) => ({
  original: "原件",
  review_pdf: "报告 PDF",
  follow_up_docx: "补问 DOCX",
  structured_json: "结构 JSON",
  archive_manifest: "归档清单",
}[type] ?? type);
