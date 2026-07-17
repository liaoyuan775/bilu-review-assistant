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

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
