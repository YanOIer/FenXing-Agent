"""fractal.render —— 把图模型渲染成单个自包含的交互式 HTML（vanilla JS + SVG）。

- 离线可开：不引用任何 CDN / 外部资源。
- 分层 DAG 布局（左 → 右），层 = 从 question 出发的最长路径深度。
- 交互：滚轮缩放（以鼠标为中心）、拖拽平移、点击节点看详情 + 高亮祖先路径。
- 分形钻取：delegate_task 节点带「⊕ 分形×N」/「⏳」徽章；双击下钻子图，
  顶部面包屑可逐级返回；pending 节点双击提示稍后刷新。全部在单 HTML 内完成。
- 数据以 `const TRACE = {...}` 递归内嵌（`</` 转义为 `<\\/`）。
"""
from __future__ import annotations

import html as _html
import json
from pathlib import Path

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
__REFRESH_META__
<title>__TITLE_HTML__</title>
<style>
  :root {
    --paper: #0d1117;
    --paper-2: #161b22;
    --ink: #e6edf3;
    --ink-2: #8b949e;
    --ink-3: #484f58;
    --line: #21262d;
    --card: #161b22;
    --accent: #58a6ff;
    --accent-glow: #1f6feb;
    --edge: #30363d;
    --edge-hl: #58a6ff;
    --neon-1: #7c3aed;
    --neon-2: #06b6d4;
    --neon-3: #f59e0b;
    --neon-4: #10b981;
    --neon-5: #ef4444;
    --toast-bg: #e6edf3;
    --toast-fg: #0d1117;
    --dot-fill: #1c2128;
    --arrow-fill: #484f58;
    --arrow-hl: #58a6ff;
    --btn-accent-bg: rgba(88,166,255,.08);
    --crumb-bg: var(--paper-2);
    --crumb-hover: rgba(88,166,255,.1);
    --crumb-cur-bg: var(--card);
  }
  [data-theme="light"] {
    --paper: #faf9f6;
    --paper-2: #f5f4f1;
    --ink: #1c1917;
    --ink-2: #57534e;
    --ink-3: #a8a29e;
    --line: #e7e5e4;
    --card: #ffffff;
    --accent: #4f46e5;
    --accent-glow: #3730a3;
    --edge: #a8a29e;
    --edge-hl: #4f46e5;
    --neon-1: #6d28d9;
    --neon-2: #0e7490;
    --neon-3: #b45309;
    --neon-4: #15803d;
    --neon-5: #b91c1c;
    --toast-bg: #1c1917;
    --toast-fg: #fafaf9;
    --dot-fill: #e6e4df;
    --arrow-fill: #a8a29e;
    --arrow-hl: #4f46e5;
    --btn-accent-bg: #eef2ff;
    --crumb-bg: #f5f4f1;
    --crumb-hover: #eceae6;
    --crumb-cur-bg: #fff;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: -apple-system, "Segoe UI", "Microsoft YaHei", "PingFang SC",
                 "Hiragino Sans GB", "Noto Sans CJK SC", "Source Han Sans SC", sans-serif;
    background: var(--paper);
    color: var(--ink);
    overflow: hidden;
  }
  #app { display: flex; flex-direction: column; width: 100vw; height: 100vh; }

  /* ---------- 顶部工具栏 ---------- */
  #toolbar {
    flex: 0 0 54px;
    display: flex; align-items: center; gap: 16px;
    padding: 0 16px;
    background: rgba(22, 27, 34, 0.72);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--line);
    z-index: 10;
  }
  .logo { font-size: 15px; font-weight: 700; letter-spacing: .5px; white-space: nowrap; }
  .logo .fx { color: var(--accent); }
  #traceTitle {
    font-size: 13px; color: var(--ink-2);
    max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    border-left: 1px solid var(--line); padding-left: 16px;
  }
  #metaChips { display: flex; gap: 8px; flex: 1; overflow: hidden; }
  .chip {
    font-size: 11.5px; color: var(--ink-2);
    background: var(--paper); border: 1px solid var(--line);
    border-radius: 999px; padding: 3px 10px; white-space: nowrap;
  }
  .chip b { color: var(--ink); font-weight: 600; }
  #toolbar .actions { display: flex; gap: 8px; }
  button {
    font: inherit; font-size: 12.5px; color: var(--ink);
    background: var(--card); border: 1px solid var(--line); border-radius: 8px;
    padding: 6px 12px; cursor: pointer;
  }
  button:hover { border-color: var(--accent); background: var(--btn-accent-bg); }
  button.active { border-color: var(--accent); color: var(--accent); background: rgba(88, 166, 255, 0.12); }

  /* ---------- 面包屑（分形钻取） ---------- */
  #breadcrumb {
    display: none; align-items: center; gap: 4px;
    padding: 5px 16px;
    background: var(--crumb-bg); border-bottom: 1px solid var(--line);
    font-size: 12px; color: var(--ink-2); z-index: 9;
  }
  #breadcrumb.show { display: flex; }
  #breadcrumb .crumb { cursor: pointer; padding: 2px 8px; border-radius: 6px; }
  #breadcrumb .crumb:hover { background: var(--crumb-hover); color: var(--ink); }
  #breadcrumb .crumb.current {
    color: var(--ink); font-weight: 600; cursor: default;
    background: var(--crumb-cur-bg); border: 1px solid var(--line);
  }
  #breadcrumb .crumb.current:hover { background: var(--crumb-cur-bg); }
  #breadcrumb .sep { color: var(--ink-3); }

  /* ---------- 主区域 ---------- */
  #stage { flex: 1; display: flex; min-height: 0; position: relative; }
  #canvas { flex: 1; display: block; cursor: grab; }
  #canvas.panning { cursor: grabbing; }

  .edge {
    fill: none; stroke: var(--edge); stroke-width: 1.5;
    filter: drop-shadow(0 0 2px rgba(88, 166, 255, 0.15));
  }
  .edge.dashed { stroke-dasharray: 6 4; }
  .edge.flowing {
    stroke-dasharray: 8 6;
    animation: flowEdge 1.5s linear infinite;
  }
  @keyframes flowEdge {
    to { stroke-dashoffset: -28; }
  }
  .edge.hl { stroke: var(--edge-hl); stroke-width: 2.4; filter: drop-shadow(0 0 6px rgba(88, 166, 255, 0.5)); }

  .node { cursor: pointer; }
  .node rect.body {
    fill: var(--card); stroke-width: 1.6; rx: 14;
    filter: drop-shadow(0 2px 8px rgba(0,0,0,.4));
  }
  .node:hover rect.body { filter: drop-shadow(0 2px 8px rgba(0,0,0,.4)) drop-shadow(0 0 10px rgba(88,166,255,.2)); }
  .node text { user-select: none; }
  .node .label { font-size: 13px; font-weight: 600; fill: var(--ink); }
  .node .sub { font-size: 10.5px; fill: var(--ink-2); }
  .node.hl rect.body { stroke: var(--accent) !important; stroke-width: 3; filter: drop-shadow(0 0 14px rgba(88,166,255,.5)) drop-shadow(0 2px 8px rgba(0,0,0,.4)); }
  .node.selected rect.body { filter: drop-shadow(0 0 16px rgba(88,166,255,.4)) drop-shadow(0 2px 8px rgba(0,0,0,.5)); }
  .glyph { font-size: 11px; font-weight: 700; fill: #fff; }
  .badge { font-weight: 700; }

  /* ---------- 详情面板 ---------- */
  #detail {
    flex: 0 0 380px;
    background: var(--card);
    border-left: 1px solid var(--line);
    display: flex; flex-direction: column;
    min-height: 0;
  }
  #detailHead {
    display: flex; align-items: center; gap: 8px;
    padding: 12px 14px; border-bottom: 1px solid var(--line);
  }
  #detailHead .kind-badge {
    font-size: 11px; font-weight: 700; color: #fff;
    border-radius: 6px; padding: 3px 8px; white-space: nowrap;
  }
  #detailHead .d-title {
    flex: 1; font-size: 13.5px; font-weight: 600;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  #detailClose { border: none; background: none; font-size: 16px; color: var(--ink-3); padding: 2px 6px; }
  #detailClose:hover { color: var(--ink); background: none; }
  #detailBody { flex: 1; overflow-y: auto; padding: 14px; }
  .d-meta { margin-bottom: 12px; }
  .d-meta .row { display: flex; font-size: 12px; padding: 4px 0; border-bottom: 1px dashed var(--line); }
  .d-meta .row .k { flex: 0 0 88px; color: var(--ink-2); }
  .d-meta .row .v { flex: 1; word-break: break-all; }
  .d-content {
    font-size: 12.8px; line-height: 1.65;
    white-space: pre-wrap; word-break: break-word;
    background: var(--paper); border: 1px solid var(--line); border-radius: 8px;
    padding: 10px 12px;
  }
  .d-hint { margin-top: 10px; font-size: 11.5px; color: var(--ink-2); }
  .d-actions { margin: 12px 0; display: flex; gap: 8px; }
  .d-actions button { border-color: var(--accent); color: var(--accent); background: var(--btn-accent-bg); }
  .d-actions button:disabled { color: var(--ink-3); border-color: var(--line); background: var(--paper); cursor: wait; }
  .d-kids { margin-top: 6px; font-size: 12px; color: var(--ink); }
  .d-kids li { margin: 3px 0 3px 18px; }
  .d-empty { color: var(--ink-3); font-size: 13px; padding: 24px 8px; text-align: center; }

  /* ---------- Toast ---------- */
  #toast {
    position: absolute; left: 50%; bottom: 28px; transform: translateX(-50%) translateY(8px);
    background: var(--toast-bg); color: var(--toast-fg); font-size: 13px;
    border-radius: 10px; padding: 10px 18px;
    opacity: 0; pointer-events: none; transition: opacity .25s, transform .25s;
    z-index: 20; box-shadow: 0 6px 20px rgba(0,0,0,.5); max-width: 70vw;
  }
  #toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
</style>
</head>
<body>
<div id="app">
  <header id="toolbar">
    <span class="logo">分形<span class="fx">Agent</span></span>
    <span id="traceTitle"></span>
    <div id="metaChips"></div>
    <div class="actions">
      <button id="btnToggleReasoning"></button>
      <button id="btnToggleTheme" title="切换亮/暗主题">🌓</button>
      <button id="btnReset">重置视图</button>
    </div>
  </header>
  <nav id="breadcrumb"></nav>
  <main id="stage">
    <svg id="canvas">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
                markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="var(--arrow-fill)"></path>
        </marker>
        <marker id="arrowHl" viewBox="0 0 10 10" refX="9" refY="5"
                markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="var(--arrow-hl)"></path>
        </marker>
        <pattern id="dots" width="26" height="26" patternUnits="userSpaceOnUse">
          <circle cx="1.4" cy="1.4" r="1.0" fill="var(--dot-fill)"></circle>
        </pattern>
      </defs>
      <g id="viewport">
        <rect id="bgDots" x="-8000" y="-8000" width="16000" height="16000" fill="url(#dots)"></rect>
        <g id="edgeLayer"></g>
        <g id="nodeLayer"></g>
      </g>
    </svg>
    <aside id="detail">
      <div id="detailHead">
        <span class="kind-badge" id="dBadge">节点</span>
        <span class="d-title" id="dTitle">详情</span>
        <button id="detailClose" title="关闭">×</button>
      </div>
      <div id="detailBody"><div class="d-empty">点击图中的节点查看完整内容</div></div>
    </aside>
    <div id="toast"></div>
  </main>
</div>
<script>
"use strict";
const TRACE = __TRACE_JSON__;
const PAGE_TITLE = __TITLE_JS__;
const RETHINK_BASE_URL = __RETHINK_URL_JS__;

const KIND_COLORS_DARK = {
  question: "#818cf8", reasoning: "#a78bfa", thought: "#22d3ee",
  tool_call: "#fbbf24", tool_result: "#34d399", answer: "#4ade80"
};
const KIND_COLORS_LIGHT = {
  question: "#3730a3", reasoning: "#6d28d9", thought: "#0e7490",
  tool_call: "#b45309", tool_result: "#15803d", answer: "#166534"
};
let KIND_COLORS = { ...KIND_COLORS_DARK };
const KIND_NAMES = {
  question: "问题", reasoning: "推理", thought: "想法",
  tool_call: "工具调用", tool_result: "工具结果", answer: "答案"
};
const KIND_GLYPH = {
  question: "问", reasoning: "推", thought: "想",
  tool_call: "具", tool_result: "果", answer: "答"
};
const NODE_W = 176, NODE_H = 58, X_GAP = 250, Y_GAP = 104, X0 = 80, Y0 = 90;
const NS = "http://www.w3.org/2000/svg";

const svg = document.getElementById("canvas");
const viewport = document.getElementById("viewport");
const edgeLayer = document.getElementById("edgeLayer");
const nodeLayer = document.getElementById("nodeLayer");
const detailBody = document.getElementById("detailBody");
const dBadge = document.getElementById("dBadge");
const dTitle = document.getElementById("dTitle");
const toastEl = document.getElementById("toast");
const btnToggle = document.getElementById("btnToggleReasoning");

let collapseReasoning = false;
let nodeMap = new Map();          // 当前视图可见节点 id -> node(带 x/y)
let edgeViews = [];               // 当前视图可见边 [{el, source, target}]
let nodeViews = new Map();        // id -> <g>
let currentEdges = [];            // 当前视图的边（供祖先高亮）
let selectedId = null;

/* 分形视图栈：根图 + 逐级下钻的子图 */
let viewStack = [{
  nodes: TRACE.nodes, edges: TRACE.edges,
  crumb: "根图", question: TRACE.question || ""
}];
function currentView() { return viewStack[viewStack.length - 1]; }

function colorOf(n) {
  if (n.kind === "tool_result" && n.meta && n.meta.status === "error") return "#f87171";
  return KIND_COLORS[n.kind] || "#57534e";
}
function truncate(s, n) {
  s = (s || "").replace(/\s+/g, " ").trim();
  return s.length > n ? s.slice(0, n) + "…" : s;
}
function el(name, attrs, parent) {
  const e = document.createElementNS(NS, name);
  if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}

/* ---------- 可见图（收起推理节点时做传递重连） ---------- */
function visibleGraph() {
  const view = currentView();
  if (!collapseReasoning) return { nodes: view.nodes.slice(), edges: view.edges.slice() };
  const hidden = new Set(view.nodes.filter(n => n.kind === "reasoning").map(n => n.id));
  const nodes = view.nodes.filter(n => !hidden.has(n.id));
  const visible = new Set(nodes.map(n => n.id));
  const out = new Map();
  view.edges.forEach(e => {
    if (!out.has(e.source)) out.set(e.source, []);
    out.get(e.source).push(e);
  });
  const seen = new Set();
  const edges = [];
  for (const n of nodes) {
    const stack = [n.id];
    const visited = new Set([n.id]);
    while (stack.length) {
      const cur = stack.pop();
      for (const e of (out.get(cur) || [])) {
        if (hidden.has(e.target)) {
          if (!visited.has(e.target)) { visited.add(e.target); stack.push(e.target); }
        } else if (visible.has(e.target)) {
          const key = n.id + "→" + e.target;
          if (!seen.has(key)) { seen.add(key); edges.push({ source: n.id, target: e.target, kind: e.kind }); }
        }
      }
    }
  }
  return { nodes, edges };
}

/* ---------- 分层 DAG 布局：层 = 从源点出发的最长路径深度 ---------- */
function layout(g) {
  const byId = new Map(g.nodes.map(n => [n.id, n]));
  const adj = new Map(g.nodes.map(n => [n.id, []]));
  const indeg = new Map(g.nodes.map(n => [n.id, 0]));
  g.edges.forEach(e => {
    if (byId.has(e.source) && byId.has(e.target)) {
      adj.get(e.source).push(e.target);
      indeg.set(e.target, indeg.get(e.target) + 1);
    }
  });
  const depth = new Map();
  const queue = g.nodes.filter(n => indeg.get(n.id) === 0).map(n => n.id);
  queue.forEach(id => depth.set(id, 0));
  while (queue.length) {
    const id = queue.shift();
    for (const t of adj.get(id)) {
      depth.set(t, Math.max(depth.get(t) || 0, (depth.get(id) || 0) + 1));
      indeg.set(t, indeg.get(t) - 1);
      if (indeg.get(t) === 0) queue.push(t);
    }
  }
  const layers = new Map();
  g.nodes.forEach(n => {
    const d = depth.get(n.id) || 0;
    if (!layers.has(d)) layers.set(d, []);
    layers.get(d).push(n);
  });
  const maxSize = Math.max.apply(null, Array.from(layers.values()).map(l => l.length));
  layers.forEach((list, d) => {
    list.forEach((n, i) => {
      n.x = X0 + d * X_GAP;
      n.y = Y0 + i * Y_GAP + (maxSize - list.length) * Y_GAP / 2;
    });
  });
}

/* ---------- 绘制 ---------- */
function drawEdge(e) {
  const s = nodeMap.get(e.source), t = nodeMap.get(e.target);
  if (!s || !t) return;
  const x1 = s.x + NODE_W, y1 = s.y + NODE_H / 2;
  const x2 = t.x, y2 = t.y + NODE_H / 2;
  const dx = Math.max(48, (x2 - x1) / 2);
  const p = el("path", {
    "class": "edge" + (e.kind === "branch" || e.kind === "merge" ? " dashed" : ""),
    "d": `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`,
    "marker-end": "url(#arrow)"
  }, edgeLayer);
  edgeViews.push({ el: p, source: e.source, target: e.target });
}

function subLine(n) {
  const step = n.meta && n.meta.msg_idx != null ? ("[步骤" + (Number(n.meta.msg_idx) + 1) + "] ") : "";
  let text = "";
  if (n.kind === "question") return step + "起点";
  if (n.kind === "answer") return step + "终点";
  if (n.kind === "tool_call") {
    if (n.children && n.children.length) text = "委派 · " + n.children.length + " 个子任务";
    else if (n.meta && n.meta.pending) text = "委派 · 子任务运行中";
    else text = "工具调用 · 可展开";
    return step + text;
  }
  if (n.kind === "tool_result") {
    const err = n.meta && n.meta.status === "error";
    return step + "工具结果 · " + (err ? "失败" : "成功");
  }
  return step + (KIND_NAMES[n.kind] || n.kind);
}

function badgeWidth(txt) {
  let w = 14;
  for (const ch of txt) w += ch.charCodeAt(0) > 255 ? 11 : 6.5;
  return Math.ceil(w);
}

/* delegate_task 节点的分形徽章：「⊕ 分形×N」或「⏳ 运行中」 */
function drawBadge(g, n, c) {
  const hasKids = !!(n.children && n.children.length);
  const isPend = !!(n.meta && n.meta.pending);
  if (!hasKids && !isPend) return;
  const txt = hasKids ? ("⊕ 分形×" + n.children.length) : "⏳ 运行中";
  const w = badgeWidth(txt);
  el("rect", { x: NODE_W - w - 2, y: -9, width: w, height: 17, rx: 8.5,
               fill: "#ffffff", stroke: c, "stroke-width": 1.2 }, g);
  const t = el("text", { "class": "badge", x: NODE_W - w / 2 - 2, y: 3.5,
                         "text-anchor": "middle", "font-size": 9.5, fill: c }, g);
  t.textContent = txt;
}

function drawNode(n) {
  const c = colorOf(n);
  const g = el("g", { "class": "node", "transform": `translate(${n.x},${n.y})` }, nodeLayer);
  el("rect", {
    "class": "body", "width": NODE_W, "height": NODE_H, "rx": 10,
    "stroke": c, "stroke-width": n.kind === "answer" ? 2.6 : 1.6
  }, g);
  el("circle", { "cx": 19, "cy": NODE_H / 2, "r": 11.5, "fill": c }, g);
  const glyph = el("text", { "class": "glyph", "x": 19, "y": NODE_H / 2 + 4, "text-anchor": "middle" }, g);
  glyph.textContent = KIND_GLYPH[n.kind] || "·";
  const label = el("text", { "class": "label", "x": 38, "y": 25 }, g);
  label.textContent = truncate(n.label, 11);
  const sub = el("text", { "class": "sub", "x": 38, "y": 43 }, g);
  sub.textContent = subLine(n);
  drawBadge(g, n, c);
  g.addEventListener("click", ev => {
    if (suppressClick) return;
    ev.stopPropagation();
    selectNode(n.id);
  });
  g.addEventListener("dblclick", ev => {
    ev.stopPropagation();
    if (n.children && n.children.length) {
      drillInto(n);
    } else if (n.meta && n.meta.pending) {
      showToast("子任务仍在后台运行，稍后在 REPL 用 /graph 刷新");
    } else if (n.expandable) {
      showToast("该工具调用没有可展开的子图");
    }
  });
  nodeViews.set(n.id, g);
}

function render() {
  const g = visibleGraph();
  layout(g);
  nodeMap = new Map(g.nodes.map(n => [n.id, n]));
  edgeViews = [];
  nodeViews = new Map();
  edgeLayer.textContent = "";
  nodeLayer.textContent = "";
  g.edges.forEach(drawEdge);
  g.nodes.forEach(drawNode);
  currentEdges = g.edges;
  selectedId = null;
  refreshToggleLabel();
}

/* ---------- 分形钻取 ---------- */
function drillInto(n) {
  if (n.children.length === 1) {
    const c = n.children[0];
    pushView({
      nodes: c.nodes, edges: c.edges,
      crumb: "子任务: " + truncate(c.question || n.label, 30),
      question: c.question || ""
    });
  } else {
    // 一次 delegate 孵化多个子 agent：命名空间隔离后同视图并列展示
    const nodes = [], edges = [];
    n.children.forEach((c, i) => {
      const p = "c" + i + "__";
      c.nodes.forEach(cn => nodes.push(Object.assign({}, cn, { id: p + cn.id })));
      c.edges.forEach(ce => edges.push({ source: p + ce.source, target: p + ce.target, kind: ce.kind }));
    });
    pushView({
      nodes: nodes, edges: edges,
      crumb: n.children.length + " 个并行子任务",
      question: n.children.map(c => c.question || "").join("；")
    });
  }
  showToast("已下钻到子图，点击顶部面包屑可返回");
}

function pushView(v) {
  viewStack.push(v);
  render();
  fitView();
  updateBreadcrumb();
  clearSelection();
}

function updateBreadcrumb() {
  const bar = document.getElementById("breadcrumb");
  bar.innerHTML = "";
  bar.classList.toggle("show", viewStack.length > 1);
  viewStack.forEach((v, i) => {
    const s = document.createElement("span");
    const isLast = i === viewStack.length - 1;
    s.className = "crumb" + (isLast ? " current" : "");
    s.textContent = v.crumb;
    if (!isLast) {
      s.addEventListener("click", () => {
        viewStack = viewStack.slice(0, i + 1);
        render();
        fitView();
        updateBreadcrumb();
        clearSelection();
      });
    }
    bar.appendChild(s);
    if (!isLast) {
      const sep = document.createElement("span");
      sep.className = "sep";
      sep.textContent = "›";
      bar.appendChild(sep);
    }
  });
  const cur = currentView();
  document.getElementById("traceTitle").textContent =
    (TRACE.id || "") + " · " + truncate(cur.question || TRACE.question, 36);
}

/* ---------- 缩放 / 平移 ---------- */
let scale = 1, tx = 0, ty = 0;
function applyTransform() {
  viewport.setAttribute("transform", `translate(${tx},${ty}) scale(${scale})`);
}
svg.addEventListener("wheel", ev => {
  ev.preventDefault();
  const rect = svg.getBoundingClientRect();
  const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
  const f = ev.deltaY < 0 ? 1.12 : 1 / 1.12;
  const ns = Math.min(4, Math.max(0.15, scale * f));
  tx = mx - (mx - tx) * (ns / scale);
  ty = my - (my - ty) * (ns / scale);
  scale = ns;
  applyTransform();
}, { passive: false });

let panning = false, moved = false, suppressClick = false, px = 0, py = 0;
svg.addEventListener("mousedown", ev => {
  if (ev.button !== 0) return;
  panning = true; moved = false;
  px = ev.clientX; py = ev.clientY;
});
window.addEventListener("mousemove", ev => {
  if (!panning) return;
  const dx = ev.clientX - px, dy = ev.clientY - py;
  if (Math.abs(dx) + Math.abs(dy) > 4) { moved = true; svg.classList.add("panning"); }
  if (moved) { tx += dx; ty += dy; px = ev.clientX; py = ev.clientY; applyTransform(); }
});
window.addEventListener("mouseup", () => {
  panning = false; svg.classList.remove("panning");
  if (moved) { suppressClick = true; setTimeout(() => { suppressClick = false; }, 90); }
  moved = false;
});
svg.addEventListener("click", () => { if (!suppressClick) clearSelection(); });

function graphBounds() {
  let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9;
  nodeMap.forEach(n => {
    minX = Math.min(minX, n.x); minY = Math.min(minY, n.y);
    maxX = Math.max(maxX, n.x + NODE_W); maxY = Math.max(maxY, n.y + NODE_H);
  });
  if (minX > maxX) return null;
  return { x: minX - 50, y: minY - 50, w: maxX - minX + 100, h: maxY - minY + 100 };
}
function fitView() {
  const b = graphBounds();
  if (!b) return;
  const rect = svg.getBoundingClientRect();
  const s = Math.min(rect.width / b.w, rect.height / b.h, 1.4);
  scale = Math.max(0.15, s);
  tx = (rect.width - b.w * scale) / 2 - b.x * scale;
  ty = (rect.height - b.h * scale) / 2 - b.y * scale;
  applyTransform();
}

/* ---------- 选中 / 祖先高亮 / 详情 ---------- */
function ancestorsOf(id) {
  const rev = new Map();
  currentEdges.forEach(e => {
    if (!rev.has(e.target)) rev.set(e.target, []);
    rev.get(e.target).push(e.source);
  });
  const seen = new Set([id]);
  const stack = [id];
  while (stack.length) {
    const cur = stack.pop();
    for (const p of (rev.get(cur) || [])) {
      if (!seen.has(p)) { seen.add(p); stack.push(p); }
    }
  }
  return seen;
}
function clearHighlight() {
  edgeViews.forEach(v => { v.el.classList.remove("hl"); v.el.setAttribute("marker-end", "url(#arrow)"); });
  nodeViews.forEach(g => g.classList.remove("hl"));
}
function clearSelection() {
  selectedId = null;
  clearHighlight();
  nodeViews.forEach(g => g.classList.remove("selected"));
  dBadge.textContent = "节点";
  dBadge.style.background = "#a8a29e";
  dTitle.textContent = "详情";
  detailBody.innerHTML = '<div class="d-empty">点击图中的节点查看完整内容</div>';
}
function selectNode(id) {
  selectedId = id;
  clearHighlight();
  nodeViews.forEach(g => g.classList.remove("selected"));
  const anc = ancestorsOf(id);
  edgeViews.forEach(v => {
    if (anc.has(v.source) && anc.has(v.target)) {
      v.el.classList.add("hl");
      v.el.setAttribute("marker-end", "url(#arrowHl)");
    }
  });
  nodeViews.forEach((g, nid) => {
    if (anc.has(nid)) g.classList.add("hl");
    if (nid === id) g.classList.add("selected");
  });
  const n = nodeMap.get(id);
  if (n) showDetail(n);
}
function metaRow(k, v) {
  const row = document.createElement("div"); row.className = "row";
  const kk = document.createElement("span"); kk.className = "k"; kk.textContent = k;
  const vv = document.createElement("span"); vv.className = "v"; vv.textContent = v;
  row.appendChild(kk); row.appendChild(vv);
  return row;
}
function showDetail(n) {
  const c = colorOf(n);
  dBadge.textContent = KIND_NAMES[n.kind] || n.kind;
  dBadge.style.background = c;
  dTitle.textContent = n.label || "";
  detailBody.innerHTML = "";
  const meta = document.createElement("div"); meta.className = "d-meta";
  meta.appendChild(metaRow("节点 id", n.id));
  if (n.meta && n.meta.msg_idx != null) meta.appendChild(metaRow("步骤编号", Number(n.meta.msg_idx) + 1));
  if (n.kind === "tool_call" && n.meta) {
    meta.appendChild(metaRow("tool_call_id", n.meta.tool_call_id || "—"));
  }
  if (n.kind === "tool_result" && n.meta) {
    meta.appendChild(metaRow("状态", n.meta.status === "error" ? "失败 (error)" : "成功 (ok)"));
    if (n.meta.tool_call_id) meta.appendChild(metaRow("tool_call_id", n.meta.tool_call_id));
  }
  if (n.meta && n.meta.chars != null) meta.appendChild(metaRow("内容长度", n.meta.chars + " 字符"));
  if (n.meta && n.meta.pending) meta.appendChild(metaRow("子任务", "后台运行中 ⏳"));
  detailBody.appendChild(meta);
  if (RETHINK_BASE_URL && n.meta && n.meta.msg_idx != null) {
    const actions = document.createElement("div"); actions.className = "d-actions";
    const btn = document.createElement("button"); btn.textContent = "重新思考此步骤";
    btn.addEventListener("click", () => rethinkNode(n, btn));
    actions.appendChild(btn);
    detailBody.appendChild(actions);
  }
  const content = document.createElement("div"); content.className = "d-content";
  content.textContent = n.content || "(空)";
  detailBody.appendChild(content);
  if (n.kind === "tool_call" && n.meta && n.meta.arguments != null) {
    const h = document.createElement("div"); h.className = "d-hint";
    h.textContent = "解析后的参数：";
    detailBody.appendChild(h);
    const args = document.createElement("div"); args.className = "d-content";
    try { args.textContent = JSON.stringify(n.meta.arguments, null, 2); }
    catch (e) { args.textContent = String(n.meta.arguments); }
    detailBody.appendChild(args);
  }
  if (n.children && n.children.length) {
    const h = document.createElement("div"); h.className = "d-hint";
    h.textContent = "双击可下钻到 " + n.children.length + " 个子任务图：";
    detailBody.appendChild(h);
    const ul = document.createElement("ul"); ul.className = "d-kids";
    n.children.forEach(c => {
      const li = document.createElement("li");
      li.textContent = truncate(c.question || "(无题)", 42);
      ul.appendChild(li);
    });
    detailBody.appendChild(ul);
  } else if (n.meta && n.meta.pending) {
    const hint = document.createElement("div"); hint.className = "d-hint";
    hint.textContent = "⏳ 子任务仍在后台运行，完成后在 REPL 输入 /graph 刷新本图。";
    detailBody.appendChild(hint);
  } else if (n.expandable) {
    const hint = document.createElement("div"); hint.className = "d-hint";
    hint.textContent = "⌘ 分形节点：delegate_task 委派节点可双击展开为子 Agent 推理子图。";
    detailBody.appendChild(hint);
  }
}

function rethinkNode(n, btn) {
  if (!RETHINK_BASE_URL) return;
  btn.disabled = true;
  btn.textContent = "重新思考中…";
  showToast("已提交重新思考请求，等待 Agent 生成新图");
  fetch(RETHINK_BASE_URL + "&node=" + encodeURIComponent(n.id), { method: "POST" })
    .then(r => r.json().then(data => ({ ok: r.ok, data })))
    .then(({ ok, data }) => {
      if (!ok || !data.ok) throw new Error(data.error || data.trace_error || "重新思考失败");
      if (data.html_path) window.location.href = "file:///" + data.html_path.replace(/\\/g, "/").replace(/^\/+/, "");
      else showToast("重新思考完成，但没有返回 HTML 路径");
    })
    .catch(err => {
      btn.disabled = false;
      btn.textContent = "重新思考此步骤";
      showToast(String(err.message || err));
    });
}

/* ---------- Toast ---------- */
let toastTimer = null;
function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove("show"), 2600);
}

/* ---------- 工具栏 ---------- */
function chip(k, v) {
  const s = document.createElement("span");
  s.className = "chip";
  const b = document.createElement("b"); b.textContent = v;
  s.appendChild(document.createTextNode(k + " "));
  s.appendChild(b);
  return s;
}
function graphMetrics(nodes, edges) {
  const byId = new Map(nodes.map(n => [n.id, n]));
  const adj = new Map(nodes.map(n => [n.id, []]));
  edges.forEach(e => {
    if (byId.has(e.source) && byId.has(e.target)) adj.get(e.source).push(e.target);
  });
  const q = nodes.find(n => n.kind === "question");
  let maxDepth = 0;
  if (q) {
    const seen = new Set([q.id]);
    const queue = [{ id: q.id, d: 0 }];
    while (queue.length) {
      const cur = queue.shift();
      maxDepth = Math.max(maxDepth, cur.d);
      for (const t of (adj.get(cur.id) || [])) {
        if (!seen.has(t)) { seen.add(t); queue.push({ id: t, d: cur.d + 1 }); }
      }
    }
  }
  const toolCalls = nodes.filter(n => n.kind === "tool_call").length;
  const branchEdges = edges.filter(e => e.kind === "branch").length;
  const memo = new Map();
  function longest(id, visiting) {
    if (memo.has(id)) return memo.get(id);
    if (visiting.has(id)) return 0;
    visiting.add(id);
    let best = 0;
    for (const t of (adj.get(id) || [])) best = Math.max(best, 1 + longest(t, visiting));
    visiting.delete(id);
    memo.set(id, best);
    return best;
  }
  let critical = 0;
  nodes.forEach(n => { critical = Math.max(critical, longest(n.id, new Set())); });
  const errors = nodes.filter(n => n.kind === "tool_result" && n.meta && n.meta.status === "error").length;
  const chars = nodes.filter(n => n.kind === "reasoning").reduce((s, n) => s + Number((n.meta || {}).chars || 0), 0);
  return { maxDepth, branchFactor: toolCalls ? (branchEdges / toolCalls).toFixed(2) : "N/A", critical, errors, chars };
}
function refreshToggleLabel() {
  const nR = currentView().nodes.filter(n => n.kind === "reasoning").length;
  btnToggle.textContent = (collapseReasoning ? "展开推理 (" : "收起推理 (") + nR + ")";
  btnToggle.classList.toggle("active", collapseReasoning);
}
function initToolbar() {
  document.title = PAGE_TITLE;
  const chips = document.getElementById("metaChips");
  const m = TRACE.meta || {};
  if (m.model) chips.appendChild(chip("模型", m.model));
  if (m.duration_s != null) chips.appendChild(chip("耗时", m.duration_s + " s"));
  if (m.api_calls != null) chips.appendChild(chip("API 调用", m.api_calls));
  chips.appendChild(chip("节点", TRACE.nodes.length));
  chips.appendChild(chip("边", TRACE.edges.length));
  const gm = graphMetrics(TRACE.nodes || [], TRACE.edges || []);
  chips.appendChild(chip("最大深度", gm.maxDepth));
  chips.appendChild(chip("分支因子", gm.branchFactor));
  chips.appendChild(chip("关键路径", gm.critical));
  chips.appendChild(chip("错误节点", gm.errors));
  chips.appendChild(chip("推理文字", gm.chars));

  btnToggle.addEventListener("click", () => {
    collapseReasoning = !collapseReasoning;
    render();
    fitView();
    clearSelection();
    if (collapseReasoning) showToast("已收起当前视图的推理节点，边已自动重连");
  });
  document.getElementById("btnReset").addEventListener("click", fitView);
  document.getElementById("detailClose").addEventListener("click", clearSelection);

  // theme toggle
  const themeBtn = document.getElementById("btnToggleTheme");
  const saved = localStorage.getItem("fractal-theme");
  if (saved === "light") {
    document.documentElement.setAttribute("data-theme", "light");
    KIND_COLORS = { ...KIND_COLORS_LIGHT };
  }
  themeBtn.addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const next = cur === "light" ? "" : "light";
    if (next) document.documentElement.setAttribute("data-theme", next);
    else document.documentElement.removeAttribute("data-theme");
    localStorage.setItem("fractal-theme", next || "dark");
    KIND_COLORS = next === "light" ? { ...KIND_COLORS_LIGHT } : { ...KIND_COLORS_DARK };
    render();
    fitView();
    clearSelection();
  });
}

window.addEventListener("resize", fitView);
initToolbar();
render();
fitView();
updateBreadcrumb();
clearSelection();
</script>
</body>
</html>
"""


def render_trace_html(trace: dict, title: str = "分形Agent · 推理轨迹",
                      auto_refresh: bool = False,
                      rethink_url: str | None = None) -> str:
    """把 trace 图模型（含递归 children）渲染成单个自包含 HTML 字符串。"""
    trace_json = json.dumps(trace, ensure_ascii=False)
    # 防止内容里的 "</script>" 提前终结脚本块
    trace_json = trace_json.replace("</", "<\\/")
    title_html = _html.escape(title or "分形Agent · 推理轨迹", quote=True)
    title_js = json.dumps(title or "分形Agent · 推理轨迹", ensure_ascii=False)
    refresh_meta = '<meta http-equiv="refresh" content="2">' if auto_refresh else ""
    rethink_url_js = json.dumps(rethink_url or "", ensure_ascii=False)
    return (
        _TEMPLATE
        .replace("__TRACE_JSON__", trace_json)
        .replace("__TITLE_HTML__", title_html)
        .replace("__TITLE_JS__", title_js)
        .replace("__REFRESH_META__", refresh_meta)
        .replace("__RETHINK_URL_JS__", rethink_url_js)
    )


def save_trace(trace: dict, html: str, out_dir) -> tuple[str, str]:
    """把 trace JSON 与 HTML 写入 out_dir，返回 (json_path, html_path)。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    trace_id = str(trace.get("id") or "turn")
    json_path = out / f"{trace_id}.json"
    html_path = out / f"{trace_id}.html"
    json_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return str(json_path), str(html_path)
