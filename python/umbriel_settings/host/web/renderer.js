// Renders Noctalia `ui.*` trees (sent by the Python host) as HTML with keyed, retained updates.
// Inputs are uncontrolled like in Noctalia: their text is only set when the element is created.
"use strict";

let bridge = null;
let glyphs = {};
const root = () => document.getElementById("root");

// ------------------------------------------------------------------ helpers
const ALIGN = { start: "flex-start", center: "center", end: "flex-end", stretch: "stretch" };
const JUSTIFY = { start: "flex-start", center: "center", end: "flex-end", space_between: "space-between" };
const WEIGHT = { thin: 100, light: 300, normal: 400, medium: 500, semibold: 600, bold: 700, heavy: 900 };

function color(value) {
  if (!value || typeof value !== "string") return "";
  if (value.startsWith("#")) return value;
  const [role, alpha] = value.split("/");
  const base = `var(--${role})`;
  return alpha ? `color-mix(in srgb, ${base} ${Math.round(parseFloat(alpha) * 100)}%, transparent)` : base;
}
function px(value) { return typeof value === "number" ? `${value}px` : ""; }
function attr(el, name, value) {
  if (value == null || value === "") el.removeAttribute(name); else el.setAttribute(name, String(value));
}

function invoke(callback, ...args) {
  if (!callback || !bridge) return;
  bridge.invoke(JSON.stringify(callback), JSON.stringify(args.map((a) => String(a))));
}

// rAF-coalesced invoke for continuous input (slider drags)
const pending = new Map();
function invokeSoon(el, callback, value) {
  pending.set(el, [callback, value]);
  if (pending.size === 1) requestAnimationFrame(() => {
    for (const [cb, v] of pending.values()) invoke(cb, v);
    pending.clear();
  });
}

// ------------------------------------------------------------------ tooltip
let tip = null;
function showTip(el) {
  const text = el.__props && el.__props.tooltip;
  if (!text) return;
  if (!tip) { tip = document.createElement("div"); tip.className = "tooltip"; document.body.appendChild(tip); }
  tip.textContent = text;
  const r = el.getBoundingClientRect();
  tip.style.display = "block";
  const top = r.bottom + 6 + tip.offsetHeight > innerHeight ? r.top - tip.offsetHeight - 6 : r.bottom + 6;
  tip.style.top = `${Math.max(4, top)}px`;
  tip.style.left = `${Math.min(Math.max(4, r.left), innerWidth - tip.offsetWidth - 4)}px`;
}
function hideTip() { if (tip) tip.style.display = "none"; }
function withTooltip(el) {
  el.addEventListener("mouseenter", () => { el.__tipTimer = setTimeout(() => showTip(el), 450); });
  el.addEventListener("mouseleave", () => { clearTimeout(el.__tipTimer); hideTip(); });
}

// ------------------------------------------------------------------ creation
const TOOLTIP_KINDS = ["column", "row", "scroll", "box", "image", "button", "dragSource"];
const CLICKABLE_KINDS = ["column", "row", "box", "image"];  // onClick makes them buttons (role, Enter/Space)

function create(node) {
  const kind = node.kind;
  let el;
  if (kind === "button") {
    el = document.createElement("button");
    el.innerHTML = '<i class="glyph" aria-hidden="true"></i><span class="text"></span>';
    el.addEventListener("click", (e) => { e.stopPropagation(); hideTip(); invoke(el.__props.onClick); });
  } else if (kind === "input") {
    el = document.createElement("input");
    el.type = "text";
    el.className = "text";
    el.value = node.props.value == null ? "" : String(node.props.value);
    el.addEventListener("input", () => invoke(el.__props.onChange, el.value));
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && el.__props.onSubmit) { e.preventDefault(); invoke(el.__props.onSubmit, el.value); }
    });
    if (node.props.focus) setTimeout(() => el.focus(), 0);
  } else if (kind === "select") {
    el = document.createElement("select");
    el.addEventListener("change", () => invoke(el.__props.onChange, el.selectedIndex));
  } else if (kind === "toggle") {
    el = document.createElement("label");
    el.className = "switch";
    el.innerHTML = '<input type="checkbox" role="switch"><span class="track" aria-hidden="true"></span>';
    el.querySelector("input").addEventListener("change", (e) => {
      const checked = e.target.checked;
      e.target.checked = !!el.__props.checked; // value-driven: the next render decides
      invoke(el.__props.onChange, checked ? "true" : "false");
    });
  } else if (kind === "slider") {
    el = document.createElement("input");
    el.type = "range";
    el.addEventListener("input", () => { fillSlider(el); invokeSoon(el, el.__props.onChange, el.value); });
    el.addEventListener("change", () => {  // the end must not overtake the last coalesced change
      const queued = pending.get(el);
      if (queued) { pending.delete(el); invoke(queued[0], queued[1]); }
      invoke(el.__props.onDragEnd, el.value);
    });
    el.addEventListener("pointerdown", () => { el.__dragging = true; });
    for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) {
      el.addEventListener(type, () => { el.__dragging = false; });
    }
  } else if (kind === "colorPicker") {
    el = document.createElement("div");
    el.className = "flex col picker";
    el.innerHTML = '<input type="color" aria-label="Color"><div class="flex rowdir alpha-row">'
      + '<span class="label">Alpha</span><input type="range" min="0" max="255" aria-label="Alpha">'
      + '<input class="text sm hex" aria-label="Hex color"></div>'
      + '<div class="flex rowdir swatches"></div>';
    const [rgb, alpha, hex] = el.querySelectorAll("input");
    const emit = (end) => {
      const value = (rgb.value + Number(alpha.value).toString(16).padStart(2, "0")).toUpperCase();
      hex.value = value;
      invoke(end ? el.__props.onChangeEnd : el.__props.onChange, value);
    };
    rgb.addEventListener("input", () => emit(false));
    rgb.addEventListener("change", () => emit(true));
    alpha.addEventListener("input", () => emit(false));
    alpha.addEventListener("change", () => emit(true));
    hex.addEventListener("change", () => {
      const v = hex.value.trim();
      if (/^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(v)) { setPicker(el, v); emit(true); }
    });
  } else if (kind === "markdown") {
    el = document.createElement("div");
    el.className = "markdown";
  } else if (kind === "label") {
    el = document.createElement("div");
    el.className = "label";
  } else if (kind === "glyph") {
    el = document.createElement("i");
    el.className = "glyph";
    el.setAttribute("aria-hidden", "true");
  } else if (kind === "image") {
    el = document.createElement("img");
    el.draggable = false;
  } else if (kind === "scroll") {
    el = document.createElement("div");
    el.className = "flex col scroll";
    const inner = document.createElement("div");
    inner.className = "inner";
    el.appendChild(inner);
    el.__host = inner;
  } else if (kind === "dragSource") {
    el = document.createElement("div");
    el.className = "drag-source";
    setupDragSource(el);  // dragdrop.js
    // the keyboard way to its click (a display tile opens its settings); dragging stays pointer-only
    el.addEventListener("keydown", (e) => {
      if (el.__props.onClick && (e.key === "Enter" || e.key === " ") && e.target === el) {
        e.preventDefault(); invoke(el.__props.onClick);
      }
    });
  } else if (kind === "dropZone") {
    el = document.createElement("div");
    el.className = "drop-zone";
  } else {
    el = document.createElement("div"); // column, row, box, separator, spacer
  }
  el.__kind = kind;
  if (TOOLTIP_KINDS.includes(kind)) withTooltip(el);
  if (CLICKABLE_KINDS.includes(kind)) {
    el.addEventListener("click", (e) => {
      if (!el.__props.onClick) return;
      e.stopPropagation(); hideTip(); invoke(el.__props.onClick);
    });
    el.addEventListener("keydown", (e) => {
      if (el.__props.onClick && (e.key === "Enter" || e.key === " ") && e.target === el) {
        e.preventDefault(); invoke(el.__props.onClick);
      }
    });
  }
  return el;
}

function fillSlider(el) {
  const min = Number(el.min), max = Number(el.max);
  el.style.setProperty("--fill", `${max > min ? ((Number(el.value) - min) / (max - min)) * 100 : 0}%`);
}

function setPicker(el, value) {
  const [rgb, alpha, hex] = el.querySelectorAll("input");
  rgb.value = value.slice(0, 7);
  alpha.value = value.length === 9 ? parseInt(value.slice(7, 9), 16) : 255;
  hex.value = value.toUpperCase();
}

// ------------------------------------------------------------------ props
const CONTAINERS = ["column", "row", "scroll", "box", "dragSource", "dropZone"];
function layout(el, p, kind) {
  const s = el.style;
  if (CONTAINERS.includes(kind)) {
    if (kind !== "box") {
      // drop zones are columns; our drag sources wrap one grip, laid out as a row
      const isRow = kind === "row" || kind === "dragSource";
      el.classList.add("flex");
      el.classList.toggle("col", !isRow);
      el.classList.toggle("rowdir", isRow);
    }
    const target = el.__host || el;  // a scroll lays out its inner column
    if (kind !== "box") {
      target.style.gap = px(p.gap);
      target.style.alignItems = ALIGN[p.align] || "stretch";
      target.style.justifyContent = JUSTIFY[p.justify] || "flex-start";
    }
    const pad = p.padding;
    target.style.padding = `${px(p.paddingV ?? pad) || 0} ${px(p.paddingH ?? pad) || 0}`;
    s.background = color(p.fill);
    s.borderRadius = px(p.radius);
    s.border = p.border ? `${p.borderWidth || 1}px solid ${color(p.border)}` : "";
    s.minWidth = px(p.minWidth);
    s.minHeight = px(p.minHeight);
    el.classList.toggle("clickable", !!p.onClick);
    el.tabIndex = p.onClick ? 0 : -1;
  }
  s.width = px(p.width);
  s.height = px(p.height);
  if (p.width != null) s.flexShrink = "0";
  s.flexGrow = p.flexGrow != null ? String(p.flexGrow) : "";
  if (p.flexGrow != null) s.flexBasis = "0";
  s.opacity = p.opacity != null ? String(p.opacity) : "";
}

// onResize (app only, not a Noctalia prop): the container reports its size as (width, height) strings whenever
// it changes, so a page can fit drawings to it; it clips what overflows, so the size follows the layout.
function watchSize(el) {
  el.classList.toggle("resize-watch", !!el.__props.onResize);
  if (!el.__props.onResize) { unwatchSize(el); return; }
  if (el.__resizeObserver) return;
  el.__resizeObserver = new ResizeObserver(() => {
    const w = Math.round(el.clientWidth), h = Math.round(el.clientHeight);
    // a container leaving the page reports 0×0 once: not a size to fit drawings to
    if (!el.isConnected || w <= 0 || h <= 0) return;
    if (!el.__props.onResize || (w === el.__reportedW && h === el.__reportedH)) return;
    el.__reportedW = w;
    el.__reportedH = h;
    invoke(el.__props.onResize, w, h);
  });
  el.__resizeObserver.observe(el);
}

function unwatchSize(el) {
  if (!el.__resizeObserver) return;
  el.__resizeObserver.disconnect();
  el.__resizeObserver = null;
  el.__reportedW = el.__reportedH = undefined;
}

function apply(el, node) {
  const p = node.props || {};
  const kind = node.kind;
  const old = el.__props || {};
  el.__props = p;
  el.dataset.key = p.key == null ? "" : String(p.key);
  layout(el, p, kind);
  if (p.onResize || el.__resizeObserver) watchSize(el);
  // Screen readers: clickable containers act as buttons; icon-only controls are named by their tooltip.
  if (CLICKABLE_KINDS.includes(kind)) {
    attr(el, "role", p.onClick ? "button" : null);
    attr(el, "aria-label", p.onClick ? p.tooltip : null);
  }
  if (kind === "dragSource") {
    attr(el, "role", p.onClick ? "button" : null);
    attr(el, "aria-label", p.tooltip);
  }
  if (kind === "label") {
    el.textContent = p.text == null ? "" : String(p.text);
    el.style.fontSize = px(p.fontSize);
    el.style.color = color(p.color);
    el.style.fontWeight = WEIGHT[p.fontWeight] || "";
    el.style.textAlign = p.textAlign || "";
    el.classList.toggle("clamp", !!p.maxLines);
    el.style.webkitLineClamp = p.maxLines ? String(p.maxLines) : "";
  } else if (kind === "glyph") {
    const code = glyphs[p.name];
    el.textContent = code ? String.fromCodePoint(code) : "";
    el.style.fontSize = px(p.size || 16);
    el.style.color = color(p.color || "on_surface");
  } else if (kind === "button") {
    el.className = [p.variant || "default", p.controlSize || "md", p.selected ? "selected" : "",
      p.glyph && !p.text ? "icon" : ""].join(" ");
    const icon = el.firstChild, text = el.lastChild;
    const code = p.glyph && glyphs[p.glyph];
    icon.textContent = code ? String.fromCodePoint(code) : "";
    icon.style.display = code ? "" : "none";
    icon.style.fontSize = px(p.controlSize === "sm" ? 16 : 18);
    text.textContent = p.text || "";
    text.style.display = p.text ? "" : "none";
    attr(el, "aria-label", p.text ? null : p.tooltip);
    attr(el, "aria-pressed", p.selected === undefined ? null : String(Boolean(p.selected)));
    if (p.fontSize) text.style.fontSize = px(p.fontSize);
    el.disabled = p.enabled === false;
  } else if (kind === "input") {
    el.classList.toggle("sm", p.controlSize === "sm");
    el.placeholder = p.placeholder || "";
    attr(el, "aria-label", p.tooltip || p.placeholder);
    el.disabled = p.enabled === false;
    if (p.fontSize) el.style.fontSize = px(p.fontSize);
  } else if (kind === "select") {
    el.classList.toggle("sm", p.controlSize === "sm");
    const options = p.options || [];
    if (JSON.stringify(options) !== JSON.stringify(old.options)) {
      el.innerHTML = "";
      for (const option of options) {
        const o = document.createElement("option");
        o.textContent = option;
        el.appendChild(o);
      }
    }
    el.selectedIndex = typeof p.selectedIndex === "number" ? p.selectedIndex : -1;
    attr(el, "aria-label", p.tooltip);
    el.disabled = p.enabled === false;
  } else if (kind === "toggle") {
    const box = el.querySelector("input");
    box.checked = !!p.checked;
    attr(box, "aria-label", p.tooltip || p.label);
    box.disabled = p.enabled === false;
  } else if (kind === "slider") {
    el.min = p.min ?? 0; el.max = p.max ?? 100; el.step = p.step ?? "any";
    if (!el.__dragging && p.value !== old.value) el.value = p.value ?? el.min;
    el.disabled = p.enabled === false;
    attr(el, "aria-label", p.tooltip);
    fillSlider(el);
  } else if (kind === "colorPicker") {
    if (p.value !== old.value && p.value) setPicker(el, p.value);
    const swatches = el.querySelector(".swatches");
    if (JSON.stringify(p.swatches) !== JSON.stringify(old.swatches)) {
      swatches.innerHTML = "";
      for (const sw of p.swatches || []) {
        const chip = document.createElement("span");
        chip.className = "swatch";
        chip.style.background = sw;
        chip.addEventListener("click", () => {
          const alpha = el.querySelectorAll("input")[1].value;
          setPicker(el, sw.slice(0, 7) + Number(alpha).toString(16).padStart(2, "0"));
          invoke(el.__props.onChangeEnd, el.querySelectorAll("input")[2].value);
        });
        swatches.appendChild(chip);
      }
    }
  } else if (kind === "markdown") {
    if (p.text !== old.text) el.innerHTML = markdown(p.text || "");
  } else if (kind === "image") {
    // each path segment is encoded: a "#", "?" or "%" in a folder name would otherwise cut the URL short
    const src = p.path ? (p.path.startsWith("/") ? `file://${p.path.split("/").map(encodeURIComponent).join("/")}` : p.path) : "";
    if (el.getAttribute("src") !== src) el.src = src;
    el.alt = p.tooltip || "";
    el.style.objectFit = p.fit || "contain";
    el.style.borderRadius = px(p.radius);
  } else if (kind === "separator") {
    el.className = "separator";
    el.style.height = px(p.thickness || 1);
    el.style.margin = `${px(p.spacing || 0)} 0`;
    el.style.alignSelf = "stretch";
    if (p.color) el.style.background = color(p.color);
  } else if (kind === "spacer") {
    if (p.flexGrow == null) el.style.flexGrow = p.width || p.height ? "" : "1";
  }
  if (kind !== "button" && p.tooltip == null) clearTimeout(el.__tipTimer);
}

// ------------------------------------------------------------------ reconciliation
function identity(node, index) {
  return node.props && node.props.key != null ? `k:${node.props.key}` : `i:${node.kind}:${index}`;
}

function patchChildren(host, children) {
  const existing = new Map();
  Array.from(host.children).forEach((el, index) => existing.set(el.__id || `x${index}`, el));
  const used = [];
  children.forEach((child, index) => {
    const id = identity(child, index);
    let el = existing.get(id);
    if (!el || el.__kind !== child.kind) {
      el = create(child);
      el.__id = id;
    } else {
      existing.delete(id);
    }
    patch(el, child);
    used.push(el);
  });
  for (const el of existing.values()) {
    unwatchSize(el);
    el.querySelectorAll(".resize-watch").forEach(unwatchSize);
    el.remove();
  }
  used.forEach((el, index) => { if (host.children[index] !== el) host.insertBefore(el, host.children[index] || null); });
}

function patch(el, node) {
  apply(el, node);
  if (CONTAINERS.includes(node.kind)) patchChildren(el.__host || el, node.children || []);
  if (node.kind === "scroll") {
    const reveal = node.props.revealKey;
    if (reveal && reveal !== el.__revealed) {
      el.__revealed = reveal;
      requestAnimationFrame(() => {
        const target = el.querySelector(`[data-key="${CSS.escape(reveal)}"]`);
        if (target) target.scrollIntoView({ block: "nearest" });
      });
    }
  }
}

function render(tree) {
  hideTip();
  const host = root();
  patchChildren(host, tree ? [tree] : []);
}

// ------------------------------------------------------------------ markdown (paragraphs, inline code/emphasis, fences)
function escapeHtml(text) {
  return text.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function inline(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}
function markdown(source) {
  const out = [];
  const lines = source.split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const fence = line.match(/^```(\w*)/);
    if (fence) {
      const body = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith("```")) { body.push(lines[i]); i += 1; }
      i += 1;
      const html = body.map((l) => {
        const cls = fence[1] === "diff" ? (l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : l.startsWith("@@") ? "hunk" : "") : "";
        return cls ? `<span class="${cls}">${escapeHtml(l)}</span>` : escapeHtml(l);
      }).join("\n");
      out.push(`<pre><code>${html}</code></pre>`);
    } else if (line.trim() === "") {
      i += 1;
    } else {
      const para = [];
      while (i < lines.length && lines[i].trim() !== "" && !lines[i].startsWith("```")) { para.push(lines[i]); i += 1; }
      out.push(`<p>${inline(para.join(" "))}</p>`);
    }
  }
  return out.join("");
}

// ------------------------------------------------------------------ keys and startup
// Ctrl+Z in a text field stays the field's own text undo; elsewhere it undoes the last settings edit.
const typing = (e) => e.target instanceof HTMLElement && e.target.matches("input[type=text]");
const KEYS = { "ctrl+f": (e) => e.ctrlKey && !e.altKey && e.key.toLowerCase() === "f",
               "ctrl+s": (e) => e.ctrlKey && !e.altKey && e.key.toLowerCase() === "s",
               "ctrl+z": (e) => e.ctrlKey && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "z" && !typing(e),
               "alt+Left": (e) => e.altKey && e.key === "ArrowLeft",
               "Escape": (e) => e.key === "Escape" && !e.ctrlKey && !e.altKey && !e.shiftKey };
document.addEventListener("keydown", (e) => {
  for (const [chord, test] of Object.entries(KEYS)) {
    if (test(e)) { e.preventDefault(); bridge && bridge.key(chord); return; }
  }
});

window.addEventListener("load", () => {
  new QWebChannel(qt.webChannelTransport, (channel) => {
    bridge = channel.objects.host;
    bridge.glyphMap.connect((json) => { glyphs = JSON.parse(json); });
    bridge.renderTree.connect((json) => render(JSON.parse(json)));
    bridge.themeCss.connect((css) => { document.getElementById("theme").textContent = css; });
    bridge.ready();
  });
});
