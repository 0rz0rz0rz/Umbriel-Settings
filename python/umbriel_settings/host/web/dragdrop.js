// Drag and drop for ui.dragSource / ui.dropZone with Noctalia's semantics: a press becomes a drag after a
// small movement (a shorter press is the source's onClick), a ghost of the previewed subtree follows the
// pointer, the accepting zone under it highlights (zones with hitSlop first, the closest wins; otherwise the
// deepest zone under the pointer) and a release there calls the zone's onDrop(payload, value). Escape or a
// release elsewhere cancels. The page owns the data: nothing moves until it renders again.
// Unlike Noctalia, the scroll area under the pointer follows it near its edges (the app's lists are long).
"use strict";

const DRAG_THRESHOLD = 4;
const SCROLL_EDGE = 48;
let drag = null;

// The element `levels` tree nodes up (a scroll's inner host div is not a tree node).
function treeAncestor(el, levels) {
  let node = el;
  for (let i = 0; i < levels; i++) {
    let parent = node.parentElement;
    while (parent && !parent.__kind) parent = parent.parentElement;
    if (!parent) break;
    node = parent;
  }
  return node;
}

function dropZones() {
  return Array.from(document.querySelectorAll(".drop-zone")).filter((zone) => {
    const p = zone.__props || {};
    return p.enabled !== false && Array.isArray(p.accepts) && p.accepts.includes(drag.type)
      && !drag.preview.contains(zone) && zone.getClientRects().length > 0;
  });
}

function zoneAt(x, y) {
  const zones = dropZones();
  let best = null, bestDistance = Infinity;
  for (const zone of zones) {
    const slop = Number(zone.__props.hitSlop) || 0;
    if (slop <= 0) continue;
    const r = zone.getBoundingClientRect();
    const distance = Math.hypot(Math.max(r.left - x, 0, x - r.right), Math.max(r.top - y, 0, y - r.bottom));
    if (distance <= slop && distance < bestDistance) { best = zone; bestDistance = distance; }
  }
  if (best) return best;
  let deepest = null;
  for (const zone of zones) {
    const r = zone.getBoundingClientRect();
    if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom && (!deepest || deepest.contains(zone))) deepest = zone;
  }
  return deepest;
}

// Un-highlights a zone and gives an expanded one its own height back.
function clearTarget(zone) {
  zone.classList.remove("drop-over");
  if (zone.__props.expandOnDrag) zone.style.height = px(zone.__props.height);
}

function setTarget(zone) {
  if (drag.target === zone) return;
  if (drag.target) clearTarget(drag.target);
  drag.target = zone;
  if (zone) {
    zone.classList.add("drop-over");
    if (zone.__props.expandOnDrag && zone.__props.height != null) {
      zone.style.height = `${Math.max(Number(zone.__props.height), drag.height)}px`;
    }
  }
}

function startDrag() {
  const source = drag.source;
  drag.preview = treeAncestor(source, Number(source.__props.previewAncestor) || 0);
  const r = drag.preview.getBoundingClientRect();
  drag.height = r.height;
  const ghost = drag.preview.cloneNode(true);
  ghost.classList.add("drag-ghost");
  ghost.removeAttribute("data-key");
  Object.assign(ghost.style, { left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px` });
  document.body.appendChild(ghost);
  drag.ghost = ghost;
  drag.offset = [drag.startX - r.left, drag.startY - r.top];
  drag.preview.classList.add(source.__props.liftFromLayout ? "drag-lifted" : "drag-dimmed");
  drag.scroller = source.closest(".scroll");
  document.body.classList.add("dragging");
  hideTip();
  drag.active = true;
  scrollLoop();
}

function moveDrag(x, y) {
  drag.x = x; drag.y = y;
  drag.ghost.style.left = `${x - drag.offset[0]}px`;
  drag.ghost.style.top = `${y - drag.offset[1]}px`;
  setTarget(zoneAt(x, y));
}

function scrollLoop() {
  if (!drag || !drag.active) return;
  const scroller = drag.scroller;
  if (scroller && drag.y != null) {
    const r = scroller.getBoundingClientRect();
    const step = drag.y < r.top + SCROLL_EDGE ? -1 : drag.y > r.bottom - SCROLL_EDGE ? 1 : 0;
    if (step) {
      const edge = step < 0 ? r.top + SCROLL_EDGE - drag.y : drag.y - (r.bottom - SCROLL_EDGE);
      const before = scroller.scrollTop;
      scroller.scrollTop += step * Math.ceil(Math.min(edge, SCROLL_EDGE) / 4);
      if (scroller.scrollTop !== before) setTarget(zoneAt(drag.x, drag.y));
    }
  }
  requestAnimationFrame(scrollLoop);
}

// Ends the drag; returns the zone to drop on (none when cancelled).
function endDrag(cancel) {
  const state = drag;
  drag = null;
  window.removeEventListener("keydown", onDragKey, true);
  if (!state || !state.active) return null;
  const target = cancel ? null : state.target;
  if (state.target) clearTarget(state.target);
  state.ghost.remove();
  state.preview.classList.remove("drag-lifted", "drag-dimmed");
  document.body.classList.remove("dragging");
  return target && target.isConnected ? target : null;
}

function onDragKey(e) {
  if (e.key !== "Escape" || !drag) return;
  e.preventDefault();
  e.stopPropagation();  // not the app's Escape (back)
  endDrag(true);
}

function setupDragSource(el) {
  el.addEventListener("pointerdown", (e) => {
    const p = el.__props;
    if (e.button !== 0 || drag || p.enabled === false) return;
    e.preventDefault();
    try { el.setPointerCapture(e.pointerId); } catch (_) { /* not a live pointer (synthetic events) */ }
    drag = { source: el, type: p.dragType, payload: p.payload, startX: e.clientX, startY: e.clientY,
             pointer: e.pointerId, active: false, target: null };
    window.addEventListener("keydown", onDragKey, true);
  });
  el.addEventListener("pointermove", (e) => {
    if (!drag || drag.source !== el || e.pointerId !== drag.pointer) return;
    if (!el.isConnected) { endDrag(true); return; }
    if (!drag.active) {
      if (Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY) < DRAG_THRESHOLD) return;
      startDrag();
    }
    moveDrag(e.clientX, e.clientY);
  });
  el.addEventListener("pointerup", (e) => {
    if (!drag || drag.source !== el || e.pointerId !== drag.pointer) return;
    const { active, payload } = drag;
    const zone = endDrag(false);
    if (!active) { if (el.__props.onClick) invoke(el.__props.onClick); return; }
    if (zone) invoke(zone.__props.onDrop, payload, zone.__props.value);
  });
  el.addEventListener("pointercancel", () => { if (drag && drag.source === el) endDrag(true); });
  // The source takes its own clicks (like Noctalia): a press on a grip neither drags nor opens its row.
  el.addEventListener("click", (e) => e.stopPropagation());
}
