/**
 * App.tsx — 笔录审查助手主应用组件。
 *
 * 页面视图管理（view 状态）:
 * - "new":        新建审查页 — 文件上传 / 演示样例选择
 * - "result":     审查结果页 — 规则列表、原文对照、人工分流
 * - "workflow":   执行流程页 — 基于 React Flow 的 DAG 工作流
 * - "history":    审查记录页 — SQLite 持久化的历史任务列表
 * - "rules":      规则管理页 — 展示全部规则定义
 * - "report":     审查报告页 — 打印/导出为 PDF
 *
 * 状态管理:
 * 使用 React useState 管理全部本地状态（无外部状态库）。
 * 后端异步任务采用轮询模式（pollReviewTask）获取进度。
 *
 * 核心交互:
 * - 上传文件 → 创建异步任务 → 轮询进度 → 自动展示结果
 * - 选择演示样例 → 本地或 Qwen 模式 → 同上
 * - 人工分流 → 提交 decision → 跳转到下一待处置项
 * - 完成复核 → 归档 → 只读
 */

import { useEffect, useMemo, useRef, useState } from "react";
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
  ClipboardCheck,
  Clock3,
  Copy,
  FileCheck2,
  FileText,
  FolderClock,
  Info,
  LoaderCircle,
  LockKeyhole,
  Radio,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Search,
  ListChecks,
  Printer,
  Settings2,
  ShieldCheck,
  Upload,
  Workflow,
  X,
} from "lucide-react";
import { acknowledgeWarnings, ApiError, archiveReview, createDemoTask, createUploadTask, generateReviewArtifacts, getDemos, getHealth, getReportData, getReviewHistory, getReviewTask, getRules, pollReviewTask, retryReviewDomain, submitFollowUpAnswer, submitIssueAction } from "./api";
import { evidenceLocationsFor, isEvidencePage, isEvidenceParagraph } from "./evidenceSelection";
import { getReviewErrorTitle } from "./errorPresentation";
import { effectiveFollowUpQuestion, formatFollowUpList } from "./followUpText";
import { canCompleteReview, nextPendingRuleId, pendingDecisionCount } from "./reviewState";
import { formatModelReviewDuration } from "./reviewTiming";
import { groupRules } from "./ruleGroups";
import { toggleSelectedRuleId } from "./resultSelection";
import type { DemoSummary, ManualStatus, ReportData, ReviewResult, ReviewSummary, ReviewTask, RuleStatus, RuleSummary, TaskStatus, VictimProfile } from "./types";
import { getVictimAvatarVariant, getVictimInitial } from "./victimProfile";
import { WorkflowView } from "./WorkflowView";
import { TemplateReviewView } from "./TemplateReviewView";
import { actionableStatuses, countTemplateStatuses } from "./templateReviewState";

// ── 常量映射表 ──────────────────────────────────────────────────

/** 规则状态 → UI 元信息（标签、CSS 类名、图标）。 */
const statusMeta: Record<RuleStatus, { label: string; className: string; icon: typeof CheckCircle2 }> = {
  covered: { label: "验证通过", className: "covered", icon: CheckCircle2 },
  missing: { label: "提问遗漏", className: "missing", icon: AlertCircle },
  incomplete: { label: "回答不完整", className: "incomplete", icon: Clock3 },
  inconsistent: { label: "事实矛盾", className: "inconsistent", icon: AlertTriangle },
  not_applicable: { label: "不适用", className: "not-applicable", icon: CircleSlash2 },
  needs_manual_review: { label: "待人工判断", className: "manual-review", icon: ShieldCheck },
};

/** 任务状态 → 中文标签。 */
const taskStatusLabel: Record<TaskStatus, string> = {
  idle: "等待上传",
  uploading: "正在读取文件",
  parsing: "正在解析笔录",
  recognizing: "正在识别图像文字",
  checking: "正在执行模板事实审查",
  validating: "正在校验证据与结果",
  completed: "审查完成",
  failed: "处理失败",
};

/** 人工处置状态 → 中文标签。 */
const manualLabel: Record<ManualStatus, string> = {
  pending: "待处理",
  confirmed: "已确认问题",
  supplemented: "已加入补问清单",
  ignored: "已忽略",
  resolved: "已补问解决",
  not_applicable: "人工确认不适用",
};

/** 创建初始（空）任务对象。 */
const createInitialTask = (): ReviewTask => ({
  id: crypto.randomUUID(),
  mode: "qwen",
  status: "idle",
  document: null,
  documentId: null,
  documentVersionId: null,
  reviewRunId: null,
  extractionPayload: null,
  victimProfile: null,
  results: [],
  failedDomains: [],
  acknowledgedWarnings: [],
  artifacts: [],
  requiredArtifacts: [],
  timings: { parseMs: null, modelReviewMs: null, modelGroupsMs: {}, totalMs: null },
  reviewStatus: "in_review",
  archivedAt: null,
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
});

/** 根组件 — 持有全部全局状态与页面路由逻辑。 */
function App() {
  const [task, setTask] = useState<ReviewTask>(createInitialTask);
  const [view, setView] = useState<"new" | "result" | "workflow" | "history" | "rules" | "report">("new");
  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);
  const [filter, setFilter] = useState<RuleStatus | "all">("all");
  const [search, setSearch] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [toast, setToast] = useState("");
  const [history, setHistory] = useState<ReviewSummary[]>([]);
  const [rules, setRules] = useState<RuleSummary[]>([]);
  const [report, setReport] = useState<ReportData | null>(null);
  const [modelHealth, setModelHealth] = useState<"checking" | "online" | "offline">("checking");
  const [documentCollapsed, setDocumentCollapsed] = useState(false);
  const [demos, setDemos] = useState<DemoSummary[]>([]);
  const [ruleCount, setRuleCount] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 初始化: 检查后端健康状态与获取演示样例列表
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

  /** 显示 Toast 消息（2.2 秒后自动消失）。 */
  const showToast = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 2200);
  };

  /**
   * 轮询等待审查任务完成，完成后自动切换到结果视图。
   *
   * 自动定位到第一个问题项（missing/incomplete）的规则详情。
   */
  const completeReview = async (taskId: string) => {
    const completed = await pollReviewTask(taskId, setTask);
    if (completed.status === "failed") {
      throw new ApiError(completed.errorCode ?? "review_service_failed", completed.errorMessage ?? "审查任务失败。");
    }
    // 自动定位到第一个问题项，如果没有问题则定位到第一条规则
    const firstProblem = completed.results.find((result) => actionableStatuses.has(result.status)) ?? completed.results[0];
    setTask(completed);
    setSelectedRuleId(firstProblem?.ruleId ?? null);
    setFilter("all");
    setSearch("");
    setDocumentCollapsed(false);
    setView("result");
  };

  /** 处理审查失败 — 将任务置为 failed 状态并显示错误。 */
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

  /** 处理文件上传审查。 */
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

  /** 处理演示样例审查。 */
  const handleDemo = async (demo: DemoSummary) => {
    if (demo.executionMode === "qwen" && modelHealth !== "online") {
      showToast("Qwen 多模态模型当前不可用，请先使用快速演示");
      return;
    }
    setTask({ ...createInitialTask(), mode: demo.executionMode, status: "checking" });
    try {
      const created = await createDemoTask(demo.id);
      setTask((current) => ({ ...current, id: created.taskId, status: "checking" }));
      await completeReview(created.taskId);
    } catch (error) {
      failReview(error);
    }
  };

  /**
   * 提交人工分流决策并自动跳转到下一待处置项。
   *
   * 使用 nextPendingRuleId 实现"已处置完一条，自动定位下一条"的交互。
   */
  const updateManualDecision = async (ruleId: string, status: ManualStatus, reason = "") => {
    try {
      const updated = await submitIssueAction(task.id, ruleId, status, reason);
      const updatedResults = task.results.map((result) => result.ruleId === ruleId ? updated : result);
      setTask((current) => ({ ...current, results: updatedResults }));
      const nextRuleId = nextPendingRuleId(updatedResults, ruleId);
      if (nextRuleId) setSelectedRuleId(nextRuleId);
      showToast(status === "supplemented" ? "已加入补问" : status === "ignored" ? "已忽略该项" : status === "resolved" ? "问题已解决" : "处理已保存");
      return true;
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "人工处理保存失败");
      return false;
    }
  };

  const saveFollowUpAnswer = async (ruleId: string, question: string, answer: string) => {
    try {
      const updated = await submitFollowUpAnswer(task.id, ruleId, question, answer);
      setTask(updated);
      setSelectedRuleId(updated.results.find((item) => actionableStatuses.has(item.status) && item.manualDecision.status === "pending")?.ruleId ?? ruleId);
      showToast("补问答案已记录，受影响业务域已重审");
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "补问答案保存失败");
      throw error;
    }
  };

  const confirmWarnings = async (codes: string[]) => {
    try {
      setTask(await acknowledgeWarnings(task.id, codes));
      showToast("解析告警已确认");
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "告警确认失败");
    }
  };

  const retryDomain = async (domain: string) => {
    try {
      setTask(await retryReviewDomain(task.id, domain));
      showToast(`${domain} 已重新审查`);
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "业务域重试失败");
    }
  };

  const generateArtifacts = async () => {
    try {
      setTask(await generateReviewArtifacts(task.id));
      showToast("归档产物已生成并完成哈希登记");
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "归档产物生成失败");
      throw error;
    }
  };

  /** 完成复核并归档（所有待处置项必须已分流）。 */
  const finishReview = async () => {
    try {
      const archived = await archiveReview(task.id);
      setTask((current) => ({ ...current, reviewStatus: archived.reviewStatus, archivedAt: archived.archivedAt }));
      showToast("本次复核已完成并自动归档");
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "完成复核失败");
    }
  };

  /** 打开审查历史。 */
  const openHistory = async () => {
    try {
      setHistory(await getReviewHistory());
      setView("history");
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "审查记录加载失败");
    }
  };

  /** 打开规则管理。 */
  const openRules = async () => {
    try {
      setRules(await getRules());
      setView("rules");
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "规则列表加载失败");
    }
  };

  const reopenHistoryItem = async (taskId: string) => {
    try {
      const restored = await getReviewTask(taskId);
      setTask(restored);
      setSelectedRuleId(restored.results.find((item) => actionableStatuses.has(item.status))?.ruleId ?? restored.results[0]?.ruleId ?? null);
      setView("result");
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "审查记录加载失败");
    }
  };

  const openReport = async () => {
    try {
      setReport(await getReportData(task.id));
      setView("report");
    } catch (error) {
      showToast(error instanceof ApiError ? error.message : "审查报告加载失败");
    }
  };

  const locateEvidence = (result: ReviewResult, requestedLocation?: ReviewResult["evidenceLocation"]) => {
    const location = requestedLocation ?? evidenceLocationsFor(result)[0];
    if (location) {
      window.setTimeout(() => {
        document
          .getElementById(`paragraph-${location.page}-${location.paragraph}`)
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
    return countTemplateStatuses(task.results);
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
            {task.status === "completed" && <span className="nav-count">{counts.missing + counts.incomplete + counts.inconsistent + counts.needs_manual_review}</span>}
          </button>
          <button className={view === "workflow" ? "nav-item active" : "nav-item"} onClick={() => setView("workflow")}>
            <Workflow size={18} /><span>执行流程</span>
          </button>
          <div className="nav-divider" />
          <button className={view === "history" ? "nav-item active" : "nav-item"} onClick={openHistory}>
            <FolderClock size={18} /><span>审查记录</span>
          </button>
          <button className={view === "rules" ? "nav-item active" : "nav-item"} onClick={openRules}>
            <Settings2 size={18} /><span>规则管理</span>
          </button>
        </nav>

          <div className="sidebar-foot">
          <LockKeyhole size={15} />
          <span>审查记录由本机 SQLite 保存</span>
        </div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <div className="mobile-brand"><ShieldCheck size={20} /><strong>笔录审查助手</strong></div>
          <div className="topbar-context">
            <span className="eyebrow">公安智能辅助审查</span>
            <span className="topbar-separator" />
            <span className="rule-version"><FileCheck2 size={15} />内部询问笔录模板 · {ruleCount || 34} 项</span>
          </div>
          <div className={`topbar-notice ${modelHealth}`}>
            <Radio size={15} />
            {modelHealth === "checking" ? "正在检查 Qwen" : modelHealth === "online" ? "Qwen 已连接" : "Qwen 未连通"}
            <span>· 结论以人工审核为准</span>
          </div>
        </header>

        {view === "workflow" ? (
          <WorkflowView task={task} />
        ) : view === "history" ? (
          <HistoryView reviews={history} onOpen={reopenHistoryItem} />
        ) : view === "rules" ? (
          <RulesView rules={rules} />
        ) : view === "report" && report ? (
          <ReportView report={report} onBack={() => setView("result")} />
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
          <TemplateReviewView
            task={task}
            selectedRuleId={selectedRuleId}
            onSelectRule={setSelectedRuleId}
            onBack={() => setView("new")}
            onAction={updateManualDecision}
            onFollowUp={saveFollowUpAnswer}
            onGenerateArtifacts={generateArtifacts}
            onArchive={finishReview}
            onShowReport={openReport}
            onAcknowledgeWarnings={confirmWarnings}
            onRetryDomain={retryDomain}
            notify={showToast}
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

/** 新建审查页面 — 文件上传区域 + 演示样例列表 + 使用边界提示。 */
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
          <p>上传规范电子笔录，系统将依据演示规则检查提问遗漏与回答不完整事项。</p>
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
          <div><h2>脱敏演示样例</h2><p>01 可快速查看完整效果，02–07 使用 Qwen 完整审查。</p></div>
          <span>共 {demos.length} 份</span>
        </div>
        <div className="sample-list">
          {demos.map((demo, index) => {
            const unavailable = demo.executionMode === "qwen" && modelHealth !== "online";
            return (
            <button key={demo.id} className="sample-row" onClick={() => onDemo(demo)} disabled={processing || unavailable}>
              <span className="sample-index">0{index + 1}</span>
              <span className="sample-file"><FileText size={18} /><span><strong>{demo.name}</strong><small>{demo.pageCount} 页 · 脱敏样例</small></span></span>
              <span className="sample-intent">{demo.intent}</span>
              <span className={`sample-mode ${demo.executionMode}`}>{demo.executionMode === "mock" ? "模拟结果" : "Qwen 完整审查"}</span>
              <ChevronRight size={18} />
            </button>
          );})}
        </div>
      </div>

      <div className="boundary-strip entrance-3">
        <ShieldCheck size={18} />
          <p><strong>使用边界</strong> 上传内容会发送到当前配置的多模态模型；仅可使用脱敏材料。结果依据内部询问笔录模板生成，不替代执法判断、案件定性或证据效力判断。旧版 DOC 请先另存为 DOCX 或 PDF。</p>
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
  locateEvidence: (result: ReviewResult, location?: ReviewResult["evidenceLocation"]) => void;
  onBack: () => void;
  updateManualDecision: (ruleId: string, status: ManualStatus, reason?: string) => Promise<boolean>;
  onComplete: () => Promise<void>;
  onShowReport: () => Promise<void>;
  documentCollapsed: boolean;
  setDocumentCollapsed: (value: boolean) => void;
  notify: (message: string) => void;
}

const profileFields: Array<{ key: keyof VictimProfile; label: string; format?: (value: VictimProfile[keyof VictimProfile]) => string }> = [
  { key: "name", label: "姓名" },
  { key: "gender", label: "性别" },
  { key: "age", label: "年龄", format: (value) => `${value}岁` },
  { key: "ethnicity", label: "民族" },
  { key: "idNumber", label: "身份证号" },
  { key: "contact", label: "联系方式" },
  { key: "employer", label: "工作单位" },
  { key: "address", label: "住址" },
];

/**
 * 被害人信息卡 — 悬浮/点击展示被害人详细信息。
 *
 * 交互方式：
 * - 悬浮（hover）: 显示弹窗，移出后自动关闭。
 * - 点击固定（click to pin）: 点击后弹窗保持打开，点击外部关闭。
 * - Escape 键: 关闭弹窗。
 *
 * 使用防内存泄漏的 useEffect 清理 pointerdown 事件监听。
 */
function VictimProfileCard({ profile }: { profile: VictimProfile }) {
  const [pinned, setPinned] = useState(false);
  const [hoverOpen, setHoverOpen] = useState(false);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const name = profile.name ?? "姓名未提取";
  const summary = [profile.gender, profile.age === null ? null : `${profile.age}岁`, profile.ethnicity].filter(Boolean).join(" · ");

  useEffect(() => {
    if (!pinned) return;
    const closeWhenClickingOutside = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setPinned(false);
    };
    document.addEventListener("pointerdown", closeWhenClickingOutside);
    return () => document.removeEventListener("pointerdown", closeWhenClickingOutside);
  }, [pinned]);

  return (
    <div
      ref={containerRef}
      className={`victim-profile ${pinned ? "is-pinned" : ""} ${hoverOpen ? "is-hover-open" : ""} ${keyboardOpen ? "is-keyboard-open" : ""}`}
      onPointerEnter={() => setHoverOpen(true)}
      onPointerLeave={() => setHoverOpen(false)}
      onFocusCapture={() => setKeyboardOpen(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setKeyboardOpen(false);
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setPinned(false);
          setHoverOpen(false);
          setKeyboardOpen(false);
        }
      }}
    >
      <button
        className="victim-profile-trigger"
        type="button"
        aria-expanded={pinned}
        aria-haspopup="dialog"
        aria-controls="victim-profile-detail"
        onClick={() => {
          setKeyboardOpen(false);
          setPinned((current) => !current);
        }}
      >
        <span className={`victim-avatar ${getVictimAvatarVariant(name)}`} aria-hidden="true">{getVictimInitial(name)}</span>
        <span className="victim-profile-summary">
          <small>被害人</small>
          <strong>{name}</strong>
          <span>{summary || "基础信息待补充"}</span>
        </span>
        <ChevronDown size={16} aria-hidden="true" />
      </button>

      <div className="victim-profile-popover" id="victim-profile-detail" role="dialog" aria-label="被害人详细信息">
        <div className="victim-profile-popover-heading">
          <span className={`victim-avatar ${getVictimAvatarVariant(name)}`} aria-hidden="true">{getVictimInitial(name)}</span>
          <span><small>被害人信息</small><strong>{name}</strong></span>
        </div>
        <dl>
          {profileFields.map(({ key, label, format }) => {
            const value = profile[key];
            return (
              <div className={key === "employer" || key === "address" ? "profile-field wide" : "profile-field"} key={key}>
                <dt>{label}</dt>
                <dd>{value === null ? "未提取" : format ? format(value) : value}</dd>
              </div>
            );
          })}
        </dl>
        <p><LockKeyhole size={13} />个人信息按笔录原文展示</p>
      </div>
    </div>
  );
}

/**
 * 审查结果页面 — 核心交互界面。
 *
 * 布局：左半栏（笔录原文） + 右半栏（规则列表与详情）。
 * 支持：
 * - 按状态过滤 / 关键词搜索。
 * - 点击规则行展开详情，高亮证据段落。
 * - 人工分流（确认/补问/忽略）。
 * - 补问清单抽屉（show/hide）。
 * - 完成复核归档。
 */
function ResultView(props: ResultViewProps) {
  const { task, counts, filter, setFilter, search, setSearch, visibleResults, selectedResult, toggleResult, locateEvidence, onBack, updateManualDecision, onComplete, onShowReport, documentCollapsed, setDocumentCollapsed, notify } = props;
  const document = task.document!;
  const [followUpsOpen, setFollowUpsOpen] = useState(false);
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [draftQuestion, setDraftQuestion] = useState("");
  const pendingCount = pendingDecisionCount(task.results);
  const followUps = task.results.filter((result) => result.manualDecision.status === "supplemented");
  const selectedEvidenceLocations = evidenceLocationsFor(selectedResult);
  const selectedEvidencePages = [...new Set(selectedEvidenceLocations.map((location) => location.page))];
  const modelReviewDuration = formatModelReviewDuration(task.timings);

  const copyText = async (text: string, successMessage: string) => {
    try {
      await navigator.clipboard.writeText(text);
      notify(successMessage);
    } catch {
      notify("复制失败，请检查浏览器剪贴板权限");
    }
  };

  const startEditing = (item: ReviewResult) => {
    setEditingRuleId(item.ruleId);
    setDraftQuestion(effectiveFollowUpQuestion(item));
  };

  const saveEditedQuestion = async (item: ReviewResult) => {
    const value = draftQuestion.trim();
    if (!value) {
      notify("补问内容不能为空");
      return;
    }
    if (await updateManualDecision(item.ruleId, "supplemented", value)) {
      setEditingRuleId(null);
      setDraftQuestion("");
      notify("补问内容已保存");
    }
  };

  return (
    <section className="result-page">
      <div className="result-header entrance-1">
        <button className="icon-button" onClick={onBack} title="返回新建审查"><ArrowLeft size={19} /></button>
        <div className="file-heading">
          <FileText size={20} />
          <div>
            <h1>{document.name}</h1>
            <p>
              {document.format} · {document.pageCount} 页 · {document.sizeLabel}
              {modelReviewDuration && ` · ${modelReviewDuration}`}
            </p>
          </div>
        </div>
        <div className="result-header-actions">
          <button className="secondary-command" onClick={() => setFollowUpsOpen((current) => !current)}><ListChecks size={16} />补问清单 <span>{followUps.length}</span></button>
          {task.reviewStatus === "archived" ? (
            <button className="primary-button compact" onClick={onShowReport}><Printer size={16} />审查报告</button>
          ) : (
            <button className="primary-button compact" disabled={!canCompleteReview(task.results)} onClick={onComplete}><Archive size={16} />完成本次复核</button>
          )}
        </div>
      </div>

      <div className={`review-completion ${task.reviewStatus === "archived" ? "archived" : ""}`}>
        {task.reviewStatus === "archived" ? (
          <><CheckCircle2 size={16} /><strong>已完成复核并自动归档</strong><span>{task.archivedAt ? new Date(task.archivedAt).toLocaleString("zh-CN") : ""}</span></>
        ) : pendingCount > 0 ? (
          <><Clock3 size={16} /><strong>还有 {pendingCount} 项待分流</strong><span>对每个提问遗漏或回答不完整项选择确认、加入补问清单或忽略。</span></>
        ) : (
          <><CheckCircle2 size={16} /><strong>全部待处置项已分流</strong><span>现在可以完成复核，系统将自动归档。</span></>
        )}
      </div>

      {followUpsOpen && (
        <section className="follow-up-drawer" aria-label="补问清单">
          <div className="follow-up-drawer-header">
            <strong>补问清单</strong><span>共 {followUps.length} 项</span>
            <div className="follow-up-header-actions">
              {followUps.length > 0 && <button className="icon-button" onClick={() => copyText(formatFollowUpList(task.results), "补问清单已复制")} title="复制全部补问"><Copy size={16} /></button>}
              <button className="icon-button" onClick={() => setFollowUpsOpen(false)} title="关闭"><X size={17} /></button>
            </div>
          </div>
          {followUps.length === 0 ? <p>尚未加入补问项。</p> : (
            <ol>{followUps.map((item) => {
              const effectiveQuestion = effectiveFollowUpQuestion(item);
              const editing = editingRuleId === item.ruleId;
              return (
                <li key={item.ruleId}>
                  <div className="follow-up-item-heading">
                    <span>{item.ruleName}</span>
                    <div className="follow-up-item-actions">
                      <button className="icon-button" onClick={() => copyText(effectiveQuestion, "该条补问已复制")} title="复制该条补问"><Copy size={15} /></button>
                      {task.reviewStatus !== "archived" && <button className="icon-button" onClick={() => startEditing(item)} title="编辑补问内容"><Pencil size={15} /></button>}
                    </div>
                  </div>
                  {editing ? (
                    <div className="follow-up-editor">
                      <textarea value={draftQuestion} onChange={(event) => setDraftQuestion(event.target.value)} aria-label={`${item.ruleName}补问内容`} />
                      <div>
                        <button className="secondary-command" onClick={() => { setEditingRuleId(null); setDraftQuestion(""); }}>取消</button>
                        <button className="primary-button compact" onClick={() => saveEditedQuestion(item)}>保存</button>
                      </div>
                    </div>
                  ) : <p>{effectiveQuestion}</p>}
                </li>
              );
            })}</ol>
          )}
        </section>
      )}

      <div className="metrics-band entrance-2">
        <div className="metrics-list">
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
        </div>
        {task.victimProfile && <VictimProfileCard profile={task.victimProfile} />}
        <div className="metric-summary"><span>需人工处理</span><strong>{counts.missing + counts.incomplete}</strong></div>
      </div>

      <div className={`review-workspace entrance-3 ${documentCollapsed ? "document-collapsed" : ""}`}>
        <section className={`document-pane ${documentCollapsed ? "collapsed" : ""}`} aria-label="笔录原文">
          <div className="pane-header">
            <div><h2>笔录原文</h2><span>{selectedEvidencePages.length > 0 ? `证据页：${selectedEvidencePages.join("、")}` : "选择问题后定位证据"}</span></div>
            <button className="icon-button muted" onClick={() => setDocumentCollapsed(!documentCollapsed)} title={documentCollapsed ? "展开原文面板" : "收起原文面板"}>
              {documentCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
            </button>
          </div>
          <div className="document-scroll">
            {document.pages.map((page) => (
              <article className={`document-page ${isEvidencePage(selectedEvidenceLocations, page.page) ? "evidence-page" : ""}`} key={page.page}>
                <div className={`page-number ${isEvidencePage(selectedEvidenceLocations, page.page) ? "selected" : ""}`}>{document.format === "DOCX" ? `逻辑页 ${page.page}` : `第 ${page.page} 页`}</div>
                {page.paragraphs.map((paragraph, index) => {
                  const isEvidence = isEvidenceParagraph(selectedEvidenceLocations, page.page, index + 1);
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
              <button className={filter === "missing" ? "active" : ""} onClick={() => setFilter("missing")}>提问遗漏</button>
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
                        <div>
                          <span>原文证据</span>
                          <div className="evidence-location-actions">
                            {evidenceLocationsFor(result).map((location) => (
                              <button key={`${location.page}-${location.paragraph}`} onClick={() => locateEvidence(result, location)}>
                                第 {location.page} 页 · 第 {location.paragraph} 段
                              </button>
                            ))}
                          </div>
                        </div>
                        <p>{result.evidence}</p>
                      </div>
                      {result.suggestedQuestion && <div className="suggestion"><span>建议补问</span><p>{result.suggestedQuestion}</p></div>}
                      {result.advisories.length > 0 && <div className="advisory-list"><span>补充关注</span><ul>{result.advisories.map((item) => <li key={item}>{item}</li>)}</ul></div>}
                      <div className="rule-source"><Info size={14} />{result.source}</div>

                      {needsAction && task.reviewStatus !== "archived" && (
                        <div className="decision-area">
                          <div className="decision-buttons">
                            <span>人工分流</span>
                            <button className={result.manualDecision.status === "confirmed" ? "selected" : ""} onClick={() => updateManualDecision(result.ruleId, "confirmed")}><Check size={15} />确认问题</button>
                            <button className={result.manualDecision.status === "supplemented" ? "selected" : ""} onClick={() => updateManualDecision(result.ruleId, "supplemented")}><ClipboardCheck size={15} />加入补问清单</button>
                            <button className={result.manualDecision.status === "ignored" ? "selected" : ""} onClick={() => updateManualDecision(result.ruleId, "ignored")}><X size={15} />忽略</button>
                          </div>
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

/** 审查历史列表 — 展示 SQLite 持久化的历史任务记录。 */
function HistoryView({ reviews, onOpen }: { reviews: ReviewSummary[]; onOpen: (taskId: string) => void }) {
  return (
    <section className="records-page">
      <header><span className="section-kicker">SQLite 持久化记录</span><h1>审查记录</h1><p>完成复核后自动归档；未完成的复核也会持续保存。</p></header>
      <div className="records-table" role="table" aria-label="审查记录">
        <div className="records-row records-heading" role="row"><span>文件</span><span>创建时间</span><span>复核状态</span><span>待分流</span><span /></div>
        {reviews.length === 0 ? <div className="records-empty">暂无审查记录</div> : reviews.map((item) => (
          <div className="records-row" role="row" key={item.id}>
            <strong>{item.documentName}</strong>
            <span>{new Date(item.createdAt).toLocaleString("zh-CN")}</span>
            <span className={`record-status ${item.reviewStatus}`}>{item.reviewStatus === "archived" ? "已归档" : "复核中"}</span>
            <span>{item.pendingCount}</span>
            <button onClick={() => onOpen(item.id)}>查看</button>
          </div>
        ))}
      </div>
    </section>
  );
}

function RulesView({ rules }: { rules: RuleSummary[] }) {
  const groups = groupRules(rules);
  return (
    <section className="rules-page">
      <header>
        <span className="section-kicker">当前生效工作口径</span>
        <h1>规则管理</h1>
        <p>本页用于核对当前七条规则。规则修改需经过业务确认和版本发布，当前仅支持查看。</p>
      </header>
      <div className="rules-groups">
        {groups.map((group) => (
          <section className="rules-group" key={group.name}>
            <div className="rules-group-heading"><strong>{group.name}</strong><span>{group.rules.length} 条</span></div>
            <div className="rules-list">
              {group.rules.map((rule) => (
                <article className="rule-item" key={rule.id}>
                  <div className="rule-item-heading">
                    <code>{rule.id}</code><strong>{rule.name}</strong>
                    <span>{rule.scope === "base" ? "基础规则" : "条件规则"}</span>
                  </div>
                  <div className="rule-item-facts">
                    <small>必查事实</small>
                    <div>{rule.requiredFacts.map((fact) => <em key={fact}>{fact}</em>)}</div>
                  </div>
                  <footer><span>分类：{rule.category}</span><span>来源：{rule.source}</span></footer>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}

/** 审查报告页面 — 支持打印/另存为 PDF。 */
function ReportView({ report, onBack }: { report: ReportData; onBack: () => void }) {
  const counts = report.results.reduce((total, item) => ({ ...total, [item.status]: total[item.status] + 1 }), {
    covered: 0, missing: 0, incomplete: 0, inconsistent: 0, not_applicable: 0, needs_manual_review: 0,
  } as Record<RuleStatus, number>);
  return (
    <section className="report-page">
      <div className="report-toolbar"><button className="icon-button" onClick={onBack} title="返回审查结果"><ArrowLeft size={18} /></button><span>审查复核报告</span><button className="primary-button compact" onClick={() => window.print()}><Printer size={16} />打印/另存为 PDF</button></div>
      <article className="report-sheet">
        <header><span>笔录辅助审查</span><h1>审查复核报告</h1><p>智能审查结果仅供复盘参考，以人工审核为准。</p></header>
        <dl className="report-meta">
          <div><dt>文件名称</dt><dd>{report.document?.name ?? "未命名笔录"}</dd></div>
          <div><dt>审查模式</dt><dd>{report.mode === "mock" ? "快速模拟演示" : report.mode === "local" ? "旧版本地演示" : "Qwen 模型"}</dd></div>
          <div><dt>审查时间</dt><dd>{new Date(report.createdAt).toLocaleString("zh-CN")}</dd></div>
          <div><dt>归档时间</dt><dd>{report.archivedAt ? new Date(report.archivedAt).toLocaleString("zh-CN") : "尚未归档"}</dd></div>
          <div><dt>复核状态</dt><dd>{report.reviewStatus === "archived" ? "已完成并归档" : "复核中"}</dd></div>
        </dl>
        {report.victimProfile && (
          <section className="report-victim">
            <h2>被害人信息</h2>
            <dl>
              {profileFields.map(({ key, label, format }) => {
                const value = report.victimProfile?.[key] ?? null;
                return <div className={key === "employer" || key === "address" ? "wide" : ""} key={key}><dt>{label}</dt><dd>{value === null ? "未提取" : format ? format(value) : value}</dd></div>;
              })}
            </dl>
          </section>
        )}
        <section className="report-summary"><h2>审查概览</h2><div><span>验证通过 <strong>{counts.covered}</strong></span><span>提问遗漏 <strong>{counts.missing}</strong></span><span>回答不完整 <strong>{counts.incomplete}</strong></span><span>不适用 <strong>{counts.not_applicable}</strong></span></div></section>
        <section className="report-results"><h2>逐项审查与人工分流</h2>{report.results.map((item) => (
          <article key={item.ruleId}>
            <div><code>{item.ruleId}</code><strong>{item.ruleName}</strong><span>{statusMeta[item.status].label}</span><em>{manualLabel[item.manualDecision.status]}</em></div>
            <p><b>判断说明：</b>{item.reason}</p>
            <p><b>原文证据：</b>{item.evidence || "未提供证据"}{evidenceLocationsFor(item).length > 0 ? `（${evidenceLocationsFor(item).map((location) => `第 ${location.page} 页第 ${location.paragraph} 段`).join("；")}）` : ""}</p>
            {(item.suggestedQuestion || item.manualDecision.reason) && <p><b>建议补问：</b>{effectiveFollowUpQuestion(item)}</p>}
          </article>
        ))}</section>
      </article>
    </section>
  );
}

export default App;
