import type { Edge, Node } from "@xyflow/react";

export interface WorkflowNodeData extends Record<string, unknown> {
  step: string;
  title: string;
  summary: string;
  input: string;
  process: string;
  output: string;
  exception: string;
  phase: "input" | "parse" | "rules" | "model" | "review" | "failure";
  status: "required" | "conditional" | "terminal";
}

export const workflowStages = [
  "validate",
  "normalize",
  "recognize",
  "three-four-review",
  "evidence-validation",
  "manual-action",
];

export const workflowNodes: Node<WorkflowNodeData>[] = [
  {
    id: "validate", type: "workflow", position: { x: 10, y: 20 },
    data: {
      step: "01", title: "文件校验", summary: "确认脱敏材料可进入审查链路。",
      input: "单份 PDF 或 DOCX，文件大小不超过 20 MB。",
      process: "校验扩展名、大小、加密状态和文件完整性。",
      output: "合法文件内容与格式元数据。",
      exception: "旧版 DOC、损坏、加密、空文档或超限文件终止任务。",
      phase: "input", status: "required",
    },
  },
  {
    id: "normalize", type: "workflow", position: { x: 280, y: 20 },
    data: {
      step: "02", title: "内容标准化", summary: "统一组织正文、表格、页面和图片。",
      input: "通过校验的 PDF 或 DOCX 二进制内容。",
      process: "提取原生文字和表格，保留真实页码或 DOCX 逻辑分页。",
      output: "带来源类型的标准文档内容块。",
      exception: "内容无法读取或页面无法渲染时终止任务。",
      phase: "parse", status: "required",
    },
  },
  {
    id: "recognize", type: "workflow", position: { x: 550, y: 20 },
    data: {
      step: "03", title: "图像文字识别", summary: "为扫描页和内嵌图片补充可核验文本。",
      input: "扫描 PDF 页面、混合页面图片和 DOCX 内嵌图片。",
      process: "调用多模态模型忠实转写，保留来源和识别置信度。",
      output: "按阅读顺序排列的 vision 内容块。",
      exception: "模型不可达、超时或响应非法时整项任务失败。",
      phase: "model", status: "conditional",
    },
  },
  {
    id: "three-four-review", type: "workflow", position: { x: 820, y: 20 },
    data: {
      step: "04", title: "三现四流审查", summary: "依据七条固定工作规则检查笔录。",
      input: "标准笔录、requiredFacts 与非强制 referenceHints。",
      process: "模型逐条判断案发现场、涉案现物、电子现痕及人员、信息、资金、行为四流。",
      output: "七条候选状态、硬缺失字段、证据和建议补问。",
      exception: "不得新增规则；补充资料不得改变硬性状态。",
      phase: "rules", status: "required",
    },
  },
  {
    id: "evidence-validation", type: "workflow", position: { x: 550, y: 245 },
    data: {
      step: "05", title: "证据与结果校验", summary: "确保每项判断都能回到规则和原文。",
      input: "七条模型结果、标准文档位置索引和规则白名单。",
      process: "校验编号、状态、硬缺失字段、证据位置，并将补充关注与遗漏统计分离。",
      output: "七条可追溯且结构稳定的审查结果。",
      exception: "规则缺失、字段越界或证据冲突时不返回部分结果。",
      phase: "review", status: "required",
    },
  },
  {
    id: "manual-action", type: "workflow", position: { x: 280, y: 245 },
    data: {
      step: "06", title: "人工复核", summary: "由办案人员确认模型结果并处置。",
      input: "规则状态、原文证据、建议补问和补充关注。",
      process: "定位原文，执行确认问题、已补问或填写原因后忽略。",
      output: "带人工处理状态的当前任务结果。",
      exception: "系统不替代执法判断、案件定性或证据效力判断。",
      phase: "review", status: "terminal",
    },
  },
  {
    id: "failed", type: "workflow", position: { x: 10, y: 245 },
    data: {
      step: "异常", title: "任务终止", summary: "输出稳定错误，不生成规则结论。",
      input: "任一关键阶段的不可恢复异常。",
      process: "记录错误类型并清空当前任务结果。",
      output: "failed 状态、错误码和可读说明。",
      exception: "不降级为本地关键词结论，不返回部分成功。",
      phase: "failure", status: "terminal",
    },
  },
];

const mainEdge = (source: string, target: string): Edge => ({
  id: `${source}-${target}`, source, target, type: "smoothstep", animated: true,
  data: { kind: "main" }, style: { stroke: "#1677ff", strokeWidth: 2 },
});

const failureEdge = (source: string): Edge => ({
  id: `${source}-failed`, source, target: "failed", type: "smoothstep", data: { kind: "failure" },
  label: "失败", style: { stroke: "#d92d20", strokeWidth: 1.5, strokeDasharray: "5 4" },
  labelStyle: { fill: "#b42318", fontSize: 10, fontWeight: 700 },
});

export const workflowEdges: Edge[] = [
  mainEdge("validate", "normalize"),
  mainEdge("normalize", "recognize"),
  mainEdge("recognize", "three-four-review"),
  mainEdge("three-four-review", "evidence-validation"),
  mainEdge("evidence-validation", "manual-action"),
  failureEdge("validate"),
  failureEdge("normalize"),
  failureEdge("recognize"),
  failureEdge("evidence-validation"),
];
