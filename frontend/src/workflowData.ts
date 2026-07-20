/**
 * 工作流图表数据 — 定义审查流程的节点、边与阶段顺序。
 *
 * 节点类型：
 * - required:    必经阶段（如文件校验、内容标准化）。
 * - conditional: 条件阶段（如图像识别仅在包含扫描页时触发）。
 * - terminal:    终态节点（人工复核、任务终止），无下游。
 *
 * 布局说明：
 * - 三列布局：左侧（validate, manual-action）、中间（normalize, evidence-validation）、
 *   右侧（recognize, template-review）。
 * - 异常节点（failed）位于左下角，与所有容错阶段以虚线相连。
 */

import { MarkerType, type Edge, type Node } from "@xyflow/react";
import type { WorkflowRuntimeState } from "./workflowProgress";

/** 工作流节点的数据结构 — 包含阶段描述与运行时状态。 */
export interface WorkflowNodeData extends Record<string, unknown> {
  step: string;          // 编号标识（如 "01", "02"）
  title: string;         // 节点标题
  summary: string;       // 一句话功能摘要
  input: string;         // 输入描述
  process: string;       // 处理逻辑描述
  output: string;        // 输出描述
  exception: string;     // 异常场景说明
  phase: "input" | "parse" | "rules" | "model" | "review" | "failure";
  status: "required" | "conditional" | "terminal";
  runtimeState?: WorkflowRuntimeState;
}

/** 工作流阶段的执行顺序标识。 */
export const workflowStages: readonly string[] = [
  "validate",              // 01 - 文件校验
  "normalize",             // 02 - 内容标准化
  "recognize",             // 03 - 图像文字识别
  "template-review",       // 04 - 模板事实与规则审查
  "evidence-validation",   // 05 - 证据与结果校验
  "manual-action",         // 06 - 人工复核
] as const;

/** 完整的工作流节点定义（含异常节点）。 */
export const workflowNodes: Node<WorkflowNodeData>[] = [
  {
    id: "validate", type: "workflow", position: { x: 20, y: 35 },
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
    id: "normalize", type: "workflow", position: { x: 310, y: 35 },
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
    id: "recognize", type: "workflow", position: { x: 600, y: 35 },
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
    id: "template-review", type: "workflow", position: { x: 600, y: 255 },
    data: {
      step: "04", title: "模板事实审查", summary: "依据内部询问笔录模板检查完整性。",
      input: "去除模板说明的问答块、稳定证据锚点和版本化模板规则。",
      process: "Qwen 按业务域抽取有证据事实，程序确定性校验适用性、必填字段、重复明细和一致性。",
      output: "模板问题状态、缺失或矛盾字段、精确证据和建议补问。",
      exception: "任一抽取域失败或证据锚点无效时不得生成完整审查。",
      phase: "rules", status: "required",
    },
  },
  {
    id: "evidence-validation", type: "workflow", position: { x: 310, y: 255 },
    data: {
      step: "05", title: "证据与结果校验", summary: "确保每项判断都能回到规则和原文。",
      input: "模板规则结果、标准文档锚点和人工处理状态。",
      process: "校验规则版本、事实状态、重复实体、证据范围和归档门槛。",
      output: "可追溯且结构稳定的模板审查问题列表。",
      exception: "规则缺失、字段越界或证据冲突时不返回部分结果。",
      phase: "review", status: "required",
    },
  },
  {
    id: "manual-action", type: "workflow", position: { x: 20, y: 255 },
    data: {
      step: "06", title: "人工复核", summary: "由办案人员确认模型结果并处置。",
      input: "规则状态、原文证据、建议补问和补充关注。",
      process: "定位原文，按类别执行补问并重审、确认不适用或说明不处理，并确保全部异常闭环。",
      output: "带人工闭环状态、可进入归档门禁的当前任务结果。",
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

/** 创建一条主流程边（蓝色实线箭头）。 */
const mainEdge = (source: string, target: string, sourceHandle: string, targetHandle: string): Edge => ({
  id: `${source}-${target}`, source, target, sourceHandle, targetHandle, type: "smoothstep", animated: true,
  data: { kind: "main" }, style: { stroke: "#1677ff", strokeWidth: 2 },
  markerEnd: { type: MarkerType.ArrowClosed, color: "#1677ff", width: 18, height: 18 },
});

/** 创建一条失败边（红色虚线，指向 failed 节点）。 */
const failureEdge = (source: string): Edge => ({
  id: `${source}-failed`, source, target: "failed", type: "smoothstep", data: { kind: "failure" },
  label: "失败", style: { stroke: "#d92d20", strokeWidth: 1.5, strokeDasharray: "5 4" },
  labelStyle: { fill: "#b42318", fontSize: 10, fontWeight: 700 },
});

/** 完整边列表（包含主流程与失败路径）。 */
export const workflowEdges: Edge[] = [
  mainEdge("validate", "normalize", "source-right", "target-left"),
  mainEdge("normalize", "recognize", "source-right", "target-left"),
  mainEdge("recognize", "template-review", "source-bottom", "target-top"),
  mainEdge("template-review", "evidence-validation", "source-left", "target-right"),
  mainEdge("evidence-validation", "manual-action", "source-left", "target-right"),
  failureEdge("validate"),
  failureEdge("normalize"),
  failureEdge("recognize"),
  failureEdge("evidence-validation"),
];

/** 用于 UI 展示的节点（过滤掉异常节点）。 */
export const displayWorkflowNodes = workflowNodes.filter((node) => workflowStages.includes(node.id));
/** 用于 UI 展示的边（仅主流程，不含失败路径）。 */
export const displayWorkflowEdges = workflowEdges.filter((edge) => edge.data?.kind === "main");
