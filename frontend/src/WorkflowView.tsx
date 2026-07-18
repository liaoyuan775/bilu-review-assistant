/**
 * WorkflowView — 审查流程可视化组件。
 *
 * 基于 React Flow (@xyflow/react) 构建的有向无环图（DAG）视图。
 * 展示审查任务的 6 个主要阶段和异常路径，支持：
 * - 节点点击查看阶段详情（输入/处理/输出）。
 * - 节点拖拽调整布局。
 * - 迷你地图导航。
 * - 实时进度状态更新（pending/active/completed/failed）。
 *
 * 状态映射：
 * - 每个节点的 runtimeState 来自 workflowProgress.getWorkflowProgress()。
 * - 边的颜色和动画根据目标节点状态动态变化。
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Bot,
  Braces,
  CheckCircle2,
  Circle,
  FileSearch,
  GitBranch,
  ListChecks,
  LoaderCircle,
  Maximize2,
  MousePointer2,
  SearchCheck,
  ShieldCheck,
  UserCheck,
  Workflow,
} from "lucide-react";

import { displayWorkflowEdges, displayWorkflowNodes, workflowStages, type WorkflowNodeData } from "./workflowData";
import { getWorkflowProgress, type WorkflowProgress, type WorkflowRuntimeState } from "./workflowProgress";
import type { ReviewTask } from "./types";

type WorkflowGraphNode = Node<WorkflowNodeData, "workflow">;

/** 节点阶段对应的图标映射。 */
const phaseIcon = {
  input: FileSearch,
  parse: SearchCheck,
  rules: GitBranch,
  model: Bot,
  review: UserCheck,
  failure: ShieldCheck,
};

/** 运行时状态对应的 UI 元信息。 */
const runtimeMeta = {
  pending: { label: "待执行", icon: Circle },
  active: { label: "执行中", icon: LoaderCircle },
  completed: { label: "已完成", icon: CheckCircle2 },
  failed: { label: "待处理", icon: Circle },
} satisfies Record<WorkflowRuntimeState, { label: string; icon: typeof Circle }>;

/** 将 WorkflowProgress 应用到节点数据中，生成带运行时状态的节点数组。 */
const nodesWithProgress = (progress: WorkflowProgress, selectedId: string): WorkflowGraphNode[] =>
  displayWorkflowNodes.map((node) => ({
    ...node,
    selected: node.id === selectedId,
    data: { ...node.data, runtimeState: progress.states[node.id as keyof WorkflowProgress["states"]] },
  })) as WorkflowGraphNode[];

/** 根据 WorkflowProgress 更新边的样式（颜色、动画）。 */
const edgesWithProgress = (progress: WorkflowProgress) => displayWorkflowEdges.map((edge) => {
  const targetState = progress.states[edge.target as keyof WorkflowProgress["states"]];
  const active = targetState === "active";
  const completed = targetState === "completed";
  return {
    ...edge,
    animated: active,
    style: {
      ...edge.style,
      stroke: active ? "#1677ff" : completed ? "#4d9b68" : "#aeb9c7",
      opacity: active || completed ? 1 : 0.55,
    },
  };
});

/** 自定义工作流节点渲染组件 — 支持 8 个连接点、阶段图标和运行时状态标识。 */
function WorkflowNode({ data, selected }: NodeProps<WorkflowGraphNode>) {
  const Icon = phaseIcon[data.phase];
  const runtimeState = data.runtimeState ?? "pending";
  const RuntimeIcon = runtimeMeta[runtimeState].icon;
  return (
    <div className={`workflow-node phase-${data.phase} state-${runtimeState} ${selected ? "selected" : ""}`}>
      {/* 8 个连接点：4 个 target + 4 个 source，支持任意方向连线 */}
      <Handle type="target" position={Position.Left} id="target-left" />
      <Handle type="target" position={Position.Right} id="target-right" />
      <Handle type="target" position={Position.Top} id="target-top" />
      <Handle type="target" position={Position.Bottom} id="target-bottom" />
      <Handle type="source" position={Position.Left} id="source-left" />
      <Handle type="source" position={Position.Right} id="source-right" />
      <Handle type="source" position={Position.Top} id="source-top" />
      <Handle type="source" position={Position.Bottom} id="source-bottom" />
      <div className="workflow-node-icon"><Icon size={17} /></div>
      <div className="workflow-node-copy">
        <div className="workflow-node-step">
          <span>{data.step}</span>
          <span><RuntimeIcon size={11} className={runtimeState === "active" ? "spin" : ""} />{runtimeMeta[runtimeState].label}</span>
        </div>
        <strong>{data.title}</strong>
        <small>{data.summary}</small>
      </div>
    </div>
  );
}

const nodeTypes = { workflow: WorkflowNode };

/** 节点详情面板要展示的字段行。 */
const detailRows = [
  { key: "input", label: "输入", icon: ArrowDownToLine },
  { key: "process", label: "处理", icon: Braces },
  { key: "output", label: "输出", icon: ArrowUpFromLine },
] as const;

/** 确定初始选中的阶段 ID。 */
const selectedStageId = (progress: WorkflowProgress, reviewStatus: ReviewTask["reviewStatus"]) =>
  progress.currentStageId && workflowStages.includes(progress.currentStageId)
    ? progress.currentStageId
    : reviewStatus === "archived"
      ? "manual-action"
      : "validate";

/** 工作流页面主组件。 */
export function WorkflowView({ task }: { task: ReviewTask }) {
  const progress = useMemo(() => getWorkflowProgress(task.status, task.reviewStatus), [task.reviewStatus, task.status]);
  const initialSelectedId = selectedStageId(progress, task.reviewStatus);
  const initialNodes = useMemo(
    () => nodesWithProgress(progress, initialSelectedId),
    [],
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(edgesWithProgress(progress));
  const [selectedId, setSelectedId] = useState<string>(initialSelectedId);
  const [instance, setInstance] = useState<ReactFlowInstance<WorkflowGraphNode> | null>(null);

  // 当任务状态或复核状态变化时，更新节点和边的运行时状态
  useEffect(() => {
    setNodes((currentNodes) => currentNodes.map((node) => ({
      ...node,
      data: { ...node.data, runtimeState: progress.states[node.id as keyof WorkflowProgress["states"]] },
    })));
    setEdges(edgesWithProgress(progress));
  }, [progress, setEdges, setNodes]);

  const selectedNode = nodes.find((node) => node.id === selectedId) ?? nodes[0];
  const selectNode = useCallback((_event: React.MouseEvent, node: WorkflowGraphNode) => {
    setSelectedId(node.id);
  }, []);

  /** 重置视图到默认布局。 */
  const resetView = () => {
    const nextSelectedId = selectedStageId(progress, task.reviewStatus);
    setNodes(nodesWithProgress(progress, nextSelectedId));
    setEdges(edgesWithProgress(progress));
    setSelectedId(nextSelectedId);
    window.setTimeout(() => instance?.fitView({ padding: 0.15, duration: 350 }), 20);
  };

  // 当前任务的整体运行状态
  const currentRuntimeState: WorkflowRuntimeState = task.reviewStatus === "archived"
      ? "completed"
      : progress.currentStageId === null || progress.currentStageId === "failed"
        ? "pending"
        : "active";
  const CurrentStateIcon = runtimeMeta[currentRuntimeState].icon;
  const currentStage = displayWorkflowNodes.find((node) => node.id === progress.currentStageId);
  const currentStepIndex = currentStage ? workflowStages.indexOf(currentStage.id) : -1;
  const liveLabel = task.reviewStatus === "archived"
      ? "审查流程已完成"
      : task.status === "failed"
        ? "等待重新处理"
      : currentStage
        ? `当前步骤：${currentStage.data.title}`
        : "等待开始";
  const stepLabel = currentStepIndex >= 0 ? `第 ${currentStepIndex + 1} / ${workflowStages.length} 步` : null;
  const updatedTime = new Date(task.updatedAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

  return (
    <section className="workflow-page">
      <header className="workflow-heading">
        <div>
          <span className="section-kicker">审查任务全链路</span>
          <h1>执行流程</h1>
          <p>沿编号和箭头查看处理进度；点击节点查看每一步的输入、处理和输出。</p>
        </div>
        <div className={`workflow-summary state-${currentRuntimeState}`} aria-live="polite">
          <span><CurrentStateIcon size={15} className={currentRuntimeState === "active" ? "spin" : ""} />{liveLabel}</span>
          <small>{stepLabel ? `${stepLabel} · ` : ""}{task.status !== "idle" ? `更新于 ${updatedTime}` : "等待新任务"}</small>
        </div>
      </header>

      <div className="workflow-workbench">
        <div className="workflow-canvas" aria-label="笔录审查执行流程图">
          <div className="workflow-canvas-toolbar">
            <span><MousePointer2 size={14} />节点可点击和拖拽</span>
            <button onClick={resetView} title="恢复默认布局"><Maximize2 size={15} />重新适配</button>
          </div>
          <ReactFlow<WorkflowGraphNode>
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={selectNode}
            onInit={setInstance}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.45}
            maxZoom={1.7}
            nodesConnectable={false}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} color="#cbd7e5" />
            <Controls showInteractive={false} position="bottom-left" />
            <MiniMap
              pannable
              zoomable
              position="bottom-right"
              nodeStrokeWidth={2}
              nodeColor={() => "#dcecff"}
              maskColor="rgba(238, 243, 248, 0.72)"
            />
          </ReactFlow>
        </div>

        <aside className={`workflow-detail phase-${selectedNode.data.phase}`} aria-live="polite">
          <div className="workflow-detail-heading">
            <div className="workflow-detail-icon">
              <Workflow size={21} />
            </div>
            <div>
              <span>执行阶段 {selectedNode.data.step} · {runtimeMeta[selectedNode.data.runtimeState ?? "pending"].label}</span>
              <h2>{selectedNode.data.title}</h2>
            </div>
          </div>
          <p className="workflow-detail-summary">{selectedNode.data.summary}</p>

          <div className="workflow-detail-list">
            {detailRows.map(({ key, label, icon: Icon }) => (
              <div className="workflow-detail-row" key={key}>
                <div><Icon size={15} /><span>{label}</span></div>
                <p>{selectedNode.data[key]}</p>
              </div>
            ))}
          </div>

          <div className="workflow-boundary-note">
            <ShieldCheck size={16} />
            <span>模型只判断已启用规则，所有结果均需人工复核。</span>
          </div>
        </aside>
      </div>

      <footer className="workflow-legend">
        <span><LoaderCircle size={13} />执行中</span>
        <span><CheckCircle2 size={13} />已完成</span>
        <span><Circle size={13} />待执行</span>
        <span><ListChecks size={14} />当前任务状态</span>
      </footer>
    </section>
  );
}
