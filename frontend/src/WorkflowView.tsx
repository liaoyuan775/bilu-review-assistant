import { useCallback, useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  AlertTriangle,
  ArrowDownToLine,
  ArrowUpFromLine,
  Bot,
  Braces,
  CheckCircle2,
  FileSearch,
  FileWarning,
  GitBranch,
  ListChecks,
  Maximize2,
  MousePointer2,
  SearchCheck,
  ShieldCheck,
  UserCheck,
  Workflow,
} from "lucide-react";

import { workflowEdges, workflowNodes, type WorkflowNodeData } from "./workflowData";

type WorkflowGraphNode = Node<WorkflowNodeData, "workflow">;

const phaseIcon = {
  input: FileSearch,
  parse: SearchCheck,
  rules: GitBranch,
  model: Bot,
  review: UserCheck,
  failure: FileWarning,
};

function WorkflowNode({ data, selected }: NodeProps<WorkflowGraphNode>) {
  const Icon = phaseIcon[data.phase];
  return (
    <div className={`workflow-node phase-${data.phase} ${selected ? "selected" : ""}`}>
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
        <span>{data.step}</span>
        <strong>{data.title}</strong>
        <small>{data.summary}</small>
      </div>
    </div>
  );
}

const nodeTypes = { workflow: WorkflowNode };

const detailRows = [
  { key: "input", label: "输入", icon: ArrowDownToLine },
  { key: "process", label: "处理", icon: Braces },
  { key: "output", label: "输出", icon: ArrowUpFromLine },
  { key: "exception", label: "异常约束", icon: AlertTriangle },
] as const;

export function WorkflowView() {
  const initialNodes = useMemo(
    () => workflowNodes.map((node) => ({ ...node, selected: node.id === "validate" })) as WorkflowGraphNode[],
    [],
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(workflowEdges);
  const [selectedId, setSelectedId] = useState("validate");
  const [instance, setInstance] = useState<ReactFlowInstance<WorkflowGraphNode> | null>(null);

  const selectedNode = nodes.find((node) => node.id === selectedId) ?? nodes[0];
  const selectNode = useCallback((_event: React.MouseEvent, node: WorkflowGraphNode) => {
    setSelectedId(node.id);
  }, []);

  const resetView = () => {
    setNodes(workflowNodes.map((node) => ({ ...node, selected: node.id === "validate" })) as WorkflowGraphNode[]);
    setSelectedId("validate");
    window.setTimeout(() => instance?.fitView({ padding: 0.15, duration: 350 }), 20);
  };

  return (
    <section className="workflow-page">
      <header className="workflow-heading">
        <div>
          <span className="section-kicker">审查任务全链路</span>
          <h1>执行流程</h1>
          <p>点击节点查看输入、处理、输出和异常边界；拖动画布或使用控件调整视图。</p>
        </div>
        <div className="workflow-summary">
          <span><CheckCircle2 size={15} />8 个主阶段</span>
          <span><AlertTriangle size={15} />4 个失败出口</span>
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
              nodeColor={(node) => node.data?.phase === "failure" ? "#fee4e2" : "#dcecff"}
              maskColor="rgba(238, 243, 248, 0.72)"
            />
          </ReactFlow>
        </div>

        <aside className={`workflow-detail phase-${selectedNode.data.phase}`} aria-live="polite">
          <div className="workflow-detail-heading">
            <div className="workflow-detail-icon">
              {selectedNode.data.phase === "failure" ? <FileWarning size={21} /> : <Workflow size={21} />}
            </div>
            <div>
              <span>{selectedNode.data.step === "异常" ? "异常出口" : `执行阶段 ${selectedNode.data.step}`}</span>
              <h2>{selectedNode.data.title}</h2>
            </div>
          </div>
          <p className="workflow-detail-summary">{selectedNode.data.summary}</p>

          <div className="workflow-detail-list">
            {detailRows.map(({ key, label, icon: Icon }) => (
              <div className={`workflow-detail-row ${key === "exception" ? "exception" : ""}`} key={key}>
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
        <span><i className="legend-main" />主处理链路</span>
        <span><i className="legend-failure" />任务失败出口</span>
        <span><ListChecks size={14} />失败任务不生成部分规则结论</span>
      </footer>
    </section>
  );
}
