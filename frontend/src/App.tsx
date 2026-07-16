import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Archive,
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleSlash2,
  ClipboardCheck,
  Clock3,
  FileCheck2,
  FileText,
  FolderClock,
  Info,
  LoaderCircle,
  LockKeyhole,
  Radio,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings2,
  ShieldCheck,
  Upload,
  Workflow,
  X,
} from "lucide-react";
import { ApiError, createDemoTask, createUploadTask, getDemos, getHealth, pollReviewTask, submitDecision } from "./api";
import { getReviewErrorTitle } from "./errorPresentation";
import { toggleSelectedRuleId } from "./resultSelection";
import type { DemoSummary, ManualStatus, ReviewResult, ReviewTask, RuleStatus, TaskStatus } from "./types";
import { WorkflowView } from "./WorkflowView";

const statusMeta: Record<RuleStatus, { label: string; className: string; icon: typeof CheckCircle2 }> = {
  covered: { label: "验证通过", className: "covered", icon: CheckCircle2 },
  missing: { label: "明确遗漏", className: "missing", icon: AlertCircle },
  incomplete: { label: "回答不完整", className: "incomplete", icon: Clock3 },
  not_applicable: { label: "不适用", className: "not-applicable", icon: CircleSlash2 },
};

const taskStatusLabel: Record<TaskStatus, string> = {
  idle: "等待上传",
  uploading: "正在读取文件",
  parsing: "正在解析笔录",
  recognizing: "正在识别图像文字",
  checking: "正在执行三现四流审查",
  validating: "正在校验证据与结果",
  completed: "审查完成",
  failed: "处理失败",
};

const manualLabel: Record<ManualStatus, string> = {
  pending: "待处理",
  confirmed: "已确认",
  supplemented: "已补问",
  ignored: "已忽略",
};

const createInitialTask = (): ReviewTask => ({
  id: crypto.randomUUID(),
  mode: "qwen",
  status: "idle",
  document: null,
  results: [],
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
});

function App() {
  const [task, setTask] = useState<ReviewTask>(createInitialTask);
  const [view, setView] = useState<"new" | "result" | "workflow">("new");
  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);
  const [filter, setFilter] = useState<RuleStatus | "all">("all");
  const [search, setSearch] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [toast, setToast] = useState("");
  const [ignoreTarget, setIgnoreTarget] = useState<string | null>(null);
  const [ignoreReason, setIgnoreReason] = useState("");
  const [modelHealth, setModelHealth] = useState<"checking" | "online" | "offline">("checking");
  const [documentCollapsed, setDocumentCollapsed] = useState(false);
  const [demos, setDemos] = useState<DemoSummary[]>([]);
  const [ruleCount, setRuleCount] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    Promise.all([getHealth(), getDemos()])
      .then(([health, demoList]) => {
        if (!active) return;
        const nextHealth = health.qwen.reachable ? "online" : "offline";
        setModelHealth(nextHealth);
        setRuleCount(health.ruleCount);
        setDemos(demoList);
      })
      .catch(() => {
        if (active) {
          setModelHealth("offline");
        }
      });
    return () => { active = false; };
  }, []);

  const showToast = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 2200);
  };

  const completeReview = async (taskId: string) => {
    const completed = await pollReviewTask(taskId, setTask);
    if (completed.status === "failed") {
      throw new ApiError(completed.errorCode ?? "review_service_failed", completed.errorMessage ?? "审查任务失败。");
    }
    const firstProblem = completed.results.find((result) => result.status === "missing" || result.status === "incomplete") ?? completed.results[0];
    setTask(completed);
    setSelectedRuleId(firstProblem?.ruleId ?? null);
    setFilter("all");
    setSearch("");
    setDocumentCollapsed(false);
    setView("result");
  };

  const failReview = (error: unknown) => {
    const parseError = error instanceof ApiError
      ? error
      : new ApiError("review_service_failed", "处理过程中发生异常，请稍后重试。");
    setTask((current) => ({
      ...current,
      status: "failed",
      results: [],
      errorCode: parseError.code,
      errorMessage: parseError.message,
    }));
    setView("new");
  };

  const handleFile = async (file: File) => {
    if (modelHealth !== "online") {
      showToast("Qwen 多模态模型当前不可用，暂不能上传审查");
      return;
    }
    setTask({ ...createInitialTask(), mode: "qwen", status: "uploading" });
    setView("new");
    try {
      const created = await createUploadTask(file);
      setTask((current) => ({ ...current, id: created.taskId, status: "parsing" }));
      await completeReview(created.taskId);
    } catch (error) {
      failReview(error);
    }
  };

  const handleDemo = async (demo: DemoSummary) => {
    setTask({ ...createInitialTask(), mode: "local", status: "checking" });
    try {
      const created = await createDemoTask(demo.id, "local");
      setTask((current) => ({ ...current, id: created.taskId, status: "checking" }));
      await completeReview(created.taskId);
    } catch (error) {
      failReview(error);
    }
  };

  const updateManualDecision = async (ruleId: string, status: ManualStatus, reason = "") => {
    try {
      const updated = await submitDecision(task.id, ruleId, status, reason);
      setTask((current) => ({ ...current, results: current.results.map((result) => result.ruleId === ruleId ? updated : result) }));
      setIgnoreTarget(null);
      setIgnoreReason("");
      showToast(status === "supplemented" ? "已标记为完成补问" : status === "ignored" ? "已记录忽略原因" : "问题已确认");
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "人工处理保存失败");
    }
  };

  const locateEvidence = (result: ReviewResult) => {
    if (result.evidenceLocation) {
      window.setTimeout(() => {
        document
          .getElementById(`paragraph-${result.evidenceLocation?.page}-${result.evidenceLocation?.paragraph}`)
          ?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 40);
    }
  };

  const toggleResult = (result: ReviewResult) => {
    const nextRuleId = toggleSelectedRuleId(selectedRuleId, result.ruleId);
    setSelectedRuleId(nextRuleId);
    if (nextRuleId) locateEvidence(result);
  };

  const selectedResult = task.results.find((result) => result.ruleId === selectedRuleId) ?? null;

  const counts = useMemo(() => {
    const base = { covered: 0, missing: 0, incomplete: 0, not_applicable: 0 };
    task.results.forEach((result) => { base[result.status] += 1; });
    return base;
  }, [task.results]);

  const visibleResults = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return task.results.filter((result) => {
      const matchesStatus = filter === "all" || result.status === filter;
      const matchesSearch = !keyword || `${result.ruleId}${result.ruleName}${result.category}${result.reason}`.toLowerCase().includes(keyword);
      return matchesStatus && matchesSearch;
    });
  }, [task.results, filter, search]);

  const processing = ["uploading", "parsing", "recognizing", "checking", "validating"].includes(task.status);

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand">
          <div className="brand-mark"><ShieldCheck size={22} strokeWidth={2.2} /></div>
          <div className="brand-copy">
            <strong>笔录审查助手</strong>
            <span>问审复盘工作台</span>
          </div>
        </div>

        <nav className="side-nav">
          <button className={view === "new" ? "nav-item active" : "nav-item"} onClick={() => setView("new")}>
            <Upload size={18} /><span>新建审查</span>
          </button>
          <button
            className={view === "result" ? "nav-item active" : "nav-item"}
            onClick={() => task.document && task.status === "completed" ? setView("result") : showToast("请先完成一份笔录审查")}
          >
            <ClipboardCheck size={18} /><span>审查结果</span>
            {task.status === "completed" && <span className="nav-count">{counts.missing + counts.incomplete}</span>}
          </button>
          <button className={view === "workflow" ? "nav-item active" : "nav-item"} onClick={() => setView("workflow")}>
            <Workflow size={18} /><span>执行流程</span>
          </button>
          <div className="nav-divider" />
          <button className="nav-item reserved" onClick={() => showToast("审查记录为后续功能预留")} title="原型预留">
            <FolderClock size={18} /><span>审查记录</span><small>预留</small>
          </button>
          <button className="nav-item reserved" onClick={() => showToast("规则管理为后续功能预留")} title="原型预留">
            <Settings2 size={18} /><span>规则管理</span><small>预留</small>
          </button>
        </nav>

          <div className="sidebar-foot">
          <LockKeyhole size={15} />
          <span>文件仅在当前任务内存处理</span>
        </div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <div className="mobile-brand"><ShieldCheck size={20} /><strong>笔录审查助手</strong></div>
          <div className="topbar-context">
            <span className="eyebrow">公安智能辅助审查</span>
            <span className="topbar-separator" />
            <span className="rule-version"><FileCheck2 size={15} />三现四流工作规则 · {ruleCount || 7} 条</span>
          </div>
          <div className={`topbar-notice ${modelHealth}`}>
            <Radio size={15} />
            {modelHealth === "checking" ? "正在检查 Qwen" : modelHealth === "online" ? "Qwen 已连接" : "Qwen 未连通"}
            <span>· 结论以人工审核为准</span>
          </div>
        </header>

        {view === "workflow" ? (
          <WorkflowView />
        ) : view === "new" ? (
          <NewReviewView
            task={task}
            processing={processing}
            isDragging={isDragging}
            setIsDragging={setIsDragging}
            fileInputRef={fileInputRef}
            onFile={handleFile}
            onDemo={handleDemo}
            modelHealth={modelHealth}
            demos={demos}
            notify={showToast}
          />
        ) : (
          <ResultView
            task={task}
            counts={counts}
            filter={filter}
            setFilter={setFilter}
            search={search}
            setSearch={setSearch}
            visibleResults={visibleResults}
            selectedResult={selectedResult}
            toggleResult={toggleResult}
            locateEvidence={locateEvidence}
            onBack={() => setView("new")}
            ignoreTarget={ignoreTarget}
            setIgnoreTarget={setIgnoreTarget}
            ignoreReason={ignoreReason}
            setIgnoreReason={setIgnoreReason}
            updateManualDecision={updateManualDecision}
            documentCollapsed={documentCollapsed}
            setDocumentCollapsed={setDocumentCollapsed}
          />
        )}
      </main>

      {toast && <div className="toast" role="status"><Check size={16} />{toast}</div>}
    </div>
  );
}

interface NewReviewViewProps {
  task: ReviewTask;
  processing: boolean;
  isDragging: boolean;
  setIsDragging: (value: boolean) => void;
  fileInputRef: React.RefObject<HTMLInputElement>;
  onFile: (file: File) => void;
  onDemo: (demo: DemoSummary) => void;
  modelHealth: "checking" | "online" | "offline";
  demos: DemoSummary[];
  notify: (message: string) => void;
}

function NewReviewView({ task, processing, isDragging, setIsDragging, fileInputRef, onFile, onDemo, modelHealth, demos, notify }: NewReviewViewProps) {
  const inputFile = (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    if (modelHealth !== "online") {
      notify("Qwen 多模态模型当前不可用，暂不能上传审查");
      return;
    }
    onFile(file);
  };

  return (
    <section className="new-review-page">
      <div className="page-heading entrance-1">
        <div>
          <span className="section-kicker">单份笔录复盘</span>
          <h1>新建审查</h1>
          <p>上传规范电子笔录，系统将依据演示规则检查漏问与回答不完整事项。</p>
        </div>
        <div className="mode-area">
          <span>文件审查引擎</span>
          <div className={`model-fixed-status ${modelHealth}`}><Radio size={15} />Qwen 多模态</div>
        </div>
      </div>

      <div
        className={`upload-workspace entrance-2 ${isDragging ? "dragging" : ""}`}
        onDragEnter={(event) => { event.preventDefault(); setIsDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => { if (event.currentTarget === event.target) setIsDragging(false); }}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragging(false);
          inputFile(event.dataTransfer.files);
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".docx,.pdf"
          hidden
          disabled={modelHealth !== "online" || processing}
          onChange={(event) => {
            inputFile(event.target.files);
            event.currentTarget.value = "";
          }}
        />
        <div className="upload-icon"><Upload size={27} /></div>
        <div className="upload-copy">
          <h2>{processing ? taskStatusLabel[task.status] : "拖拽笔录到此处"}</h2>
          <p>{processing
            ? "正在调用模型并校验证据，请勿关闭页面"
            : "支持文本型、扫描型或混合 PDF，以及含正文、表格、图片的 DOCX，单份不超过 20 MB"}</p>
        </div>
        {processing ? (
          <div className="processing-line"><LoaderCircle size={18} className="spin" /><span>{taskStatusLabel[task.status]}</span></div>
        ) : (
          <button className="primary-button" disabled={modelHealth !== "online"} onClick={() => fileInputRef.current?.click()}><FileText size={17} />选择文件</button>
        )}
      </div>

      {task.status === "failed" && (
        <div className="error-banner entrance-2" role="alert">
          <AlertCircle size={19} />
          <div><strong>{getReviewErrorTitle(task.errorCode)}</strong><span>{task.errorMessage}</span></div>
          <button onClick={() => fileInputRef.current?.click()}>重新选择</button>
        </div>
      )}

      <div className="sample-section entrance-3">
        <div className="section-heading-row">
          <div><h2>脱敏演示样例</h2><p>无需模型连接，直接查看七条规则与证据联动。</p></div>
          <span>共 3 份</span>
        </div>
        <div className="sample-list">
          {demos.map((demo, index) => (
            <button key={demo.id} className="sample-row" onClick={() => onDemo(demo)} disabled={processing}>
              <span className="sample-index">0{index + 1}</span>
              <span className="sample-file"><FileText size={18} /><span><strong>{demo.name}</strong><small>{demo.pageCount} 页 · 脱敏样例</small></span></span>
              <span className="sample-intent">{demo.intent}</span>
              <ChevronRight size={18} />
            </button>
          ))}
        </div>
      </div>

      <div className="boundary-strip entrance-3">
        <ShieldCheck size={18} />
          <p><strong>使用边界</strong> 上传内容会发送到当前配置的多模态模型；仅可使用脱敏材料。结果依据三现四流工作口径生成，不替代执法判断、案件定性或证据效力判断。旧版 DOC 请先另存为 DOCX 或 PDF。</p>
      </div>
    </section>
  );
}

interface ResultViewProps {
  task: ReviewTask;
  counts: Record<RuleStatus, number>;
  filter: RuleStatus | "all";
  setFilter: (value: RuleStatus | "all") => void;
  search: string;
  setSearch: (value: string) => void;
  visibleResults: ReviewResult[];
  selectedResult: ReviewResult | null;
  toggleResult: (result: ReviewResult) => void;
  locateEvidence: (result: ReviewResult) => void;
  onBack: () => void;
  ignoreTarget: string | null;
  setIgnoreTarget: (value: string | null) => void;
  ignoreReason: string;
  setIgnoreReason: (value: string) => void;
  updateManualDecision: (ruleId: string, status: ManualStatus, reason?: string) => Promise<void>;
  documentCollapsed: boolean;
  setDocumentCollapsed: (value: boolean) => void;
}

function ResultView(props: ResultViewProps) {
  const { task, counts, filter, setFilter, search, setSearch, visibleResults, selectedResult, toggleResult, locateEvidence, onBack, ignoreTarget, setIgnoreTarget, ignoreReason, setIgnoreReason, updateManualDecision, documentCollapsed, setDocumentCollapsed } = props;
  const document = task.document!;

  return (
    <section className="result-page">
      <div className="result-header entrance-1">
        <button className="icon-button" onClick={onBack} title="返回新建审查"><ArrowLeft size={19} /></button>
        <div className="file-heading">
          <FileText size={20} />
          <div><h1>{document.name}</h1><p>{document.format} · {document.pageCount} 页 · {document.sizeLabel}</p></div>
        </div>
        <div className="completed-label"><CheckCircle2 size={16} />审查完成</div>
      </div>

      <div className="metrics-band entrance-2">
        {(Object.keys(statusMeta) as RuleStatus[]).map((status) => {
          const meta = statusMeta[status];
          const Icon = meta.icon;
          return (
            <button key={status} className={`metric ${filter === status ? "selected" : ""}`} onClick={() => setFilter(filter === status ? "all" : status)}>
              <Icon size={19} className={meta.className} />
              <span><strong>{counts[status]}</strong><small>{meta.label}</small></span>
            </button>
          );
        })}
        <div className="metric-summary"><span>需人工处理</span><strong>{counts.missing + counts.incomplete}</strong></div>
      </div>

      <div className={`review-workspace entrance-3 ${documentCollapsed ? "document-collapsed" : ""}`}>
        <section className={`document-pane ${documentCollapsed ? "collapsed" : ""}`} aria-label="笔录原文">
          <div className="pane-header">
            <div><h2>笔录原文</h2><span>{selectedResult?.evidenceLocation ? `已定位至第 ${selectedResult.evidenceLocation.page} 页` : "选择问题后定位证据"}</span></div>
            <button className="icon-button muted" onClick={() => setDocumentCollapsed(!documentCollapsed)} title={documentCollapsed ? "展开原文面板" : "收起原文面板"}>
              {documentCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
            </button>
          </div>
          <div className="document-scroll">
            {document.pages.map((page) => (
              <article className="document-page" key={page.page}>
                <div className="page-number">{document.format === "DOCX" ? `逻辑页 ${page.page}` : `第 ${page.page} 页`}</div>
                {page.paragraphs.map((paragraph, index) => {
                  const isEvidence = selectedResult?.evidenceLocation?.page === page.page && selectedResult.evidenceLocation.paragraph === index + 1;
                  return (
                    <p id={`paragraph-${page.page}-${index + 1}`} className={isEvidence ? "evidence-highlight" : ""} key={`${page.page}-${index}`}>
                      <span className="paragraph-index">{index + 1}</span>
                      <span className="paragraph-text">{paragraph.text}</span>
                      {paragraph.sourceType !== "native_text" && (
                        <small className={`source-chip ${paragraph.sourceType}`}>
                          {paragraph.sourceType === "table" ? "表格" : `图像识别${paragraph.confidence === null ? "" : ` ${Math.round(paragraph.confidence * 100)}%`}`}
                        </small>
                      )}
                    </p>
                  );
                })}
              </article>
            ))}
          </div>
        </section>

        <section className="review-pane" aria-label="审查结果">
          <div className="review-tools">
            <div className="search-box"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索规则或问题" /></div>
            <div className="filter-control">
              <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>全部</button>
              <button className={filter === "missing" ? "active" : ""} onClick={() => setFilter("missing")}>漏问</button>
              <button className={filter === "incomplete" ? "active" : ""} onClick={() => setFilter("incomplete")}>不完整</button>
            </div>
          </div>

          <div className="result-list">
            {visibleResults.length === 0 && <div className="empty-results"><Search size={24} /><span>没有符合当前条件的规则</span></div>}
            {(["三现", "四流"] as const).map((group) => {
              const groupResults = visibleResults.filter((result) => result.group === group);
              if (groupResults.length === 0) return null;
              return <section className="result-group" key={group}>
                <div className="result-group-heading"><strong>{group}</strong><span>{groupResults.length} 项</span></div>
                {groupResults.map((result) => {
              const meta = statusMeta[result.status];
              const StatusIcon = meta.icon;
              const isSelected = result.ruleId === selectedResult?.ruleId;
              const needsAction = result.status === "missing" || result.status === "incomplete";
              return (
                <article key={result.ruleId} className={`result-row ${isSelected ? "selected" : ""}`}>
                  <button
                    className="result-row-summary"
                    onClick={() => toggleResult(result)}
                    aria-expanded={isSelected}
                    aria-controls={`result-detail-${result.ruleId}`}
                  >
                    <StatusIcon size={18} className={meta.className} />
                    <span className="result-title"><span><code>{result.ruleId}</code><small>{result.group}</small></span><strong>{result.ruleName}</strong></span>
                    <span className={`status-label ${meta.className}`}>{meta.label}</span>
                    {result.manualDecision.status !== "pending" && <span className="manual-chip">{manualLabel[result.manualDecision.status]}</span>}
                    {isSelected ? <ChevronDown size={17} /> : <ChevronRight size={17} />}
                  </button>

                  {isSelected && (
                    <div className="result-detail" id={`result-detail-${result.ruleId}`}>
                      <div className="detail-block"><span>判断说明</span><p>{result.reason}</p></div>
                      {result.missingFacts.length > 0 && <div className="fact-list"><span>缺失要素</span><div>{result.missingFacts.map((fact) => <em key={fact}>{fact}</em>)}</div></div>}
                      <div className="evidence-box">
                        <div><span>原文证据</span>{result.evidenceLocation && <button onClick={() => locateEvidence(result)}>第 {result.evidenceLocation.page} 页 · 定位</button>}</div>
                        <p>{result.evidence}</p>
                      </div>
                      {result.suggestedQuestion && <div className="suggestion"><span>建议补问</span><p>{result.suggestedQuestion}</p></div>}
                      {result.advisories.length > 0 && <div className="advisory-list"><span>补充关注</span><ul>{result.advisories.map((item) => <li key={item}>{item}</li>)}</ul></div>}
                      <div className="rule-source"><Info size={14} />{result.source}</div>

                      {needsAction && (
                        <div className="decision-area">
                          {ignoreTarget === result.ruleId ? (
                            <div className="ignore-form">
                              <label htmlFor={`ignore-${result.ruleId}`}>填写忽略原因</label>
                              <textarea id={`ignore-${result.ruleId}`} value={ignoreReason} onChange={(event) => setIgnoreReason(event.target.value)} placeholder="例如：已通过其他材料核实" autoFocus />
                              <div><button className="text-button" onClick={() => { setIgnoreTarget(null); setIgnoreReason(""); }}>取消</button><button className="danger-button" disabled={!ignoreReason.trim()} onClick={() => updateManualDecision(result.ruleId, "ignored", ignoreReason.trim())}>确认忽略</button></div>
                            </div>
                          ) : (
                            <div className="decision-buttons">
                              <span>人工处理</span>
                              <button onClick={() => updateManualDecision(result.ruleId, "confirmed")}><Check size={15} />确认问题</button>
                              <button onClick={() => updateManualDecision(result.ruleId, "supplemented")}><ClipboardCheck size={15} />已补问</button>
                              <button onClick={() => { setIgnoreTarget(result.ruleId); setIgnoreReason(result.manualDecision.reason); }}><X size={15} />忽略</button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </article>
              );
                })}
              </section>;
            })}
          </div>
        </section>
      </div>
    </section>
  );
}

export default App;
