/**
 * 应用入口 — 挂载 React 根节点并引入全局样式。
 *
 * StrictMode 在开发环境下启用双渲染以检测副作用问题。
 * 生产构建后，StrictMode 的双渲染不会生效。
 */
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

class BootErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <pre style={{ margin: 0, padding: 24, font: "14px/1.5 sans-serif", color: "#b42318", whiteSpace: "pre-wrap" }}>
          页面加载失败：{this.state.error.message}
        </pre>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BootErrorBoundary>
      <App />
    </BootErrorBoundary>
  </React.StrictMode>,
);
