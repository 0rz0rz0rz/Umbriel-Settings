-- The Outputs page: display arrangement geometry (lib/arrange.luau, lib/displays.luau) and the page flows
-- (numbered tiles, drag and drop, the default star, Tidy up, display names, mode dropdowns).
-- Usage: lua outputs_test.lua PLUGIN_DIR FIXTURE_DIR   (fixtures come from the real helper, see test_panel.py)
local H = dofile((arg[0]:match("^(.*)/") or ".") .. "/harness.lua")
local entry = H.start("panel.luau")
local json, replies, loaded, pluginDir = H.json, H.replies, H.loaded, H.pluginDir
local flushReads, hasText, find, clickText, screen, byKey = H.flushReads, H.hasText, H.find, H.clickText, H.screen, H.byKey

local arrange = dofile(pluginDir .. "/lib/arrange.luau")
local displays = dofile(pluginDir .. "/lib/displays.luau")

local function rect(id, x, y, w, h) return { id = id, x = x, y = y, w = w, h = h } end
local function at(positions, id, x, y)
  local p = positions[id]
  assert(p and p.x == x and p.y == y, string.format("%s at %s,%s, expected %d,%d", id,
    p and tostring(p.x) or "?", p and tostring(p.y) or "?", x, y))
end

-- ------------------------------------------------------------------ geometry
local main, side = rect("DP-1", 0, 0, 2560, 1440), rect("HDMI-A-1", 2560, 0, 1920, 1080)
local rects = { main, rect("DP-2", 5000, 0, 1920, 1080), side }
-- dropped on the top edge: centered above, the rest centered on the main display too, top-left at 0,0
local moved = arrange.move(rects, "DP-2", "DP-1", "above")
at(moved, "DP-1", 0, 1080); at(moved, "DP-2", 320, 0); at(moved, "HDMI-A-1", 2560, 1260)
local function applied(positions)
  local out = {}
  for _, r in ipairs(rects) do table.insert(out, rect(r.id, positions[r.id].x, positions[r.id].y, r.w, r.h)) end
  return out
end
-- a second display on the same edge: the pair is centered on the main display
local pair = arrange.move(applied(moved), "HDMI-A-1", "DP-1", "above")
at(pair, "DP-2", 0, 0); at(pair, "HDMI-A-1", 1920, 0); at(pair, "DP-1", 640, 1080)
-- the left edge of a display in that row puts the other one before it in the row
local before = arrange.move(applied(moved), "HDMI-A-1", "DP-2", "left")
at(before, "HDMI-A-1", 0, 0); at(before, "DP-2", 1920, 0); at(before, "DP-1", 640, 1080)
-- the top edge of a display in that row stacks on it instead
local stacked = arrange.move(applied(moved), "HDMI-A-1", "DP-2", "above")
at(stacked, "HDMI-A-1", 320, 0); at(stacked, "DP-2", 320, 1080); at(stacked, "DP-1", 0, 2160)
-- a laid-out arrangement reads back as the same tree
local tidy = arrange.tidy(applied(pair))
for id, p in pairs(pair) do at(tidy, id, p.x, p.y) end
-- a corner: above, hanging off that half (its edge on the main display's center line)
local corner = arrange.move(rects, "DP-2", "DP-1", "above-end")
at(corner, "DP-1", 0, 1080); at(corner, "DP-2", 1280, 0); at(corner, "HDMI-A-1", 2560, 1260)
local cornerLeft = arrange.move(rects, "DP-2", "DP-1", "above-start")
at(cornerLeft, "DP-2", 0, 0); at(cornerLeft, "DP-1", 640, 1080); at(cornerLeft, "HDMI-A-1", 3200, 1260)
-- read back from positions, a corner stays a corner
for _, laid in ipairs({ corner, cornerLeft }) do
  local again = arrange.tidy(applied(laid))
  for id, p in pairs(laid) do at(again, id, p.x, p.y) end
end
-- both corners meet on the center line: read back, that is one centered row
local both = arrange.move(applied(corner), "HDMI-A-1", "DP-1", "above-start")
at(both, "HDMI-A-1", 0, 0); at(both, "DP-2", 1920, 0); at(both, "DP-1", 640, 1080)
local again = arrange.tidy(applied(both))
for id, p in pairs(both) do at(again, id, p.x, p.y) end
-- dropping a display on itself or an unknown one changes nothing
assert(arrange.move(rects, "DP-1", "DP-1", "left") == nil and arrange.move(rects, "DP-1", "DP-9", "left") == nil)
-- a group that would overlap an earlier one is pushed outward
local crowded = { rect("R", 0, 0, 2000, 2000), rect("W", -1000, -500, 4000, 500), rect("L", -1000, 500, 1000, 1000),
                  rect("T", -700, -100, 400, 600) }  -- T sits on L and reaches into W
local pushed = arrange.tidy(crowded)
at(pushed, "W", 0, 600); at(pushed, "R", 1000, 1100); at(pushed, "L", 0, 1600); at(pushed, "T", 300, 0)
-- drawing bands: a plus shape cuts into rows and columns, a pinwheel can't be cut
local plus = arrange.bands({ rect("1", 10, 10, 10, 10), rect("2", 10, 20, 10, 10), rect("3", 0, 12, 10, 6),
                             rect("4", 20, 10, 10, 10), rect("5", 10, 0, 10, 10) })
assert(plus and plus.dir == "row" and #plus.parts == 3 and plus.parts[2].dir == "column", "plus shape bands")
assert(arrange.bands({ rect("a", 0, 0, 2, 1), rect("b", 2, 0, 1, 2), rect("c", 1, 2, 2, 1), rect("d", 0, 1, 1, 2) })
       == nil, "a pinwheel has no straight cut")

-- modes and sizes
local w, h, rate = displays.parseMode("2560x1440@164.999")
assert(w == 2560 and h == 1440 and rate == 164.999)
w, h, rate = displays.parseMode("1920x1080")
assert(w == 1920 and h == 1080 and rate == nil)
assert(displays.parseMode("preferred") == nil and displays.parseMode("1920x1080@fast") == nil)
local acme = { name = "DP-1", config_name = "Acme 1", scale = 1, transform = "normal",
  logical_size = { width = 2560, height = 1440 }, position = { x = 0, y = 0 },
  modes = { { width = 2560, height = 1440, refresh_mhz = 164999, current = true },
            { width = 2560, height = 1440, refresh_mhz = 60000, preferred = true },
            { width = 1920, height = 1080, refresh_mhz = 60000 },
            { width = 1920, height = 1080, refresh_mhz = 60000 } } }
local size = displays.logicalSize({ live = acme, values = {} })
assert(size.w == 2560 and size.h == 1440, "the live logical size while nothing overrides it")
size = displays.logicalSize({ live = acme, values = { scale = 1.25, transform = "90" } })
assert(size.w == 1152 and size.h == 2048, "scaled and turned: " .. size.w .. "x" .. size.h)
local modes = displays.modes(acme)
assert(#modes == 2 and modes[1].label == "2560×1440" and #modes[2].rates == 1, "resolutions without duplicates")
assert(modes[1].rates[1].text == "164.999" and modes[1].rates[2].preferred, "fastest rate first")

-- identical monitors without a serial number report one name: their entries go by connector instead
local twins = displays.list({ { name = "DP-1", config_name = "Twin" }, { name = "DP-2", config_name = "Twin" } },
  { { name = "Twin", values = {} } })
assert(twins[1].entryName == "DP-1" and twins[2].entryName == "DP-2", "twins are named by connector")
assert(not twins[1].index and not twins[2].index and not displays.forEntry(twins, "Twin"), "neither takes the entry")

-- ------------------------------------------------------------------ page
local function output(name, monitor, x, w0, h0)
  return { name = name, config_name = monitor, scale = 1, transform = "normal", enabled = true,
    logical_size = { width = w0, height = h0 }, position = { x = x, y = 0 },
    modes = { { width = w0, height = h0, refresh_mhz = 60000, current = true, preferred = true },
              { width = w0, height = h0, refresh_mhz = 144000 } } }
end
local live = { acme, output("DP-2", "Acme 2", 5000, 1920, 1080), output("HDMI-A-1", nil, 2560, 1920, 1080) }
replies.outputs = function() return true, json.encode({ outputs = live }) end
entry.onOpen()
flushReads()
local store = loaded[pluginDir .. "/lib/store.luau"]
clickText("Outputs")
for _, id in ipairs({ "DP-1", "DP-2", "HDMI-A-1" }) do
  assert(find("dragSource", function(n) return n.props.key == "display-" .. id end), "tile for " .. id)
end
assert(hasText("1") and hasText("2") and hasText("3"), "numbered by connector: " .. screen())
assert(byKey("display-tidy").props.enabled, "positions that aren't centered can be tidied up")
-- the drawing fills the page (no scrolling, nothing under it)
local page = H.walk(H.tree(), function(n) return tostring(n.props.key):match("^content%-fill%-") ~= nil end)
assert(page and page.kind == "column", "the Outputs page doesn't scroll")
assert(page.children[#page.children].props.key == "display-canvas", "the drawing is last")
assert(not byKey("display-default") and not byKey("display-move"), "no Default display or Move rows")
-- only the middle of a tile is the drag source (Noctalia's covers its subtree): the star and zones are outside
local function insideSource(key)
  return H.walk(H.tree(), function(n)
    return n.kind == "dragSource" and H.walk(n, function(c) return c ~= n and c.props.key == key end) ~= nil
  end) ~= nil
end
assert(not insideSource("display-star-DP-1") and not insideSource("display-above-DP-1"), "clickable star")
assert(byKey("display-canvas").props.flexGrow == 1 and not byKey("display-canvas").props.onResize,
  "the canvas takes the free height; the panel has no size reports")
-- the panel's fixed size: 6920×1440 px of displays fill 880 px of width
assert(byKey("display-tile-DP-1").props.width == 326, "tile width " .. tostring(byKey("display-tile-DP-1").props.width))

-- a click on a display without an entry adds one, which goes again when its page is left untouched
byKey("display-DP-2").props.onClick()
flushReads()
assert(#store.entryItems("output") == 1 and hasText("Acme 2"), screen())
H.goHome()
assert(#store.entryItems("output") == 0 and #store.entryOps == 0 and #store.history == 0, "nothing left behind")
clickText("Outputs")

-- a click opens the display's entry, created under the monitor's name
byKey("display-DP-1").props.onClick()
flushReads()
local items = store.entryItems("output")
assert(#items == 1 and items[1].name == "Acme 1", "entry named after the monitor")
assert(hasText("Acme 1") and hasText("Outputs · 1 of 1 · Display 1"), screen())
assert(not pcall(H.input, "^dup%-output"), "no “Name for a copy” box on an output")

-- the mode is two dropdowns: resolution, then refresh rate (in Basics; groups start closed)
clickText("Basics")
local function select(suffix)
  return find("select", function(n) return tostring(n.props.key):match(suffix) ~= nil end)
end
local resolution = select(":resolution$")
assert(resolution.props.options[1] == "Preferred" and resolution.props.selectedIndex == 0,
  table.concat(resolution.props.options, ","))
assert(select(":rate$").props.enabled == false and select(":rate$").props.options[1] == "60 Hz",
  "the preferred rate, not editable while the mode is unset")
resolution.props.onChange("2")
local last = store.entryOps[#store.entryOps]
assert(last.field == "mode" and last.value == "1920x1080@60", tostring(last.value))
resolution = select(":resolution$")
resolution.props.onChange("1")
assert(store.entryOps[#store.entryOps].value == "2560x1440@164.999", "the fastest rate first")
assert(select(":resolution$").props.selectedIndex == 1, "the set resolution is selected")
local rateSelect = select(":rate$")
assert(rateSelect.props.selectedIndex == 0 and rateSelect.props.options[2] == "60 Hz (preferred)",
  table.concat(rateSelect.props.options, ","))
rateSelect.props.onChange("1")
assert(store.entryOps[#store.entryOps].value == "2560x1440@60")
-- a mode Umbriel doesn't report is shown as itself
store.entryOp("output", { op = "set", index = 0, field = "mode", value = "1280x1024@75" })
H.goHome()
clickText("Outputs")
byKey("display-DP-1").props.onClick()
flushReads()
resolution = select(":resolution$")
assert(resolution.props.options[#resolution.props.options] == "1280x1024@75 (not reported)"
       and resolution.props.selectedIndex == #resolution.props.options - 1, "unreported mode kept")
store.entryOp("output", { op = "unset", index = 0, field = "mode" })

-- dropping a display on an edge writes every display's position as one undo step
H.goHome()
clickText("Outputs")
local steps = #store.history
H.drag("display-DP-2", "display-above-DP-1")
assert(#store.history == steps + 1, "one undo step")
local function positions()
  local found = {}
  for _, item in ipairs(store.entryItems("output")) do found[item.name] = item.values.position end
  return found
end
local pos = positions()
assert(pos["Acme 1"].x == 0 and pos["Acme 1"].y == 1080, "main below: " .. json.encode(pos))
assert(pos["Acme 2"].x == 320 and pos["Acme 2"].y == 0, "dropped display centered above")
assert(pos["HDMI-A-1"].x == 2560 and pos["HDMI-A-1"].y == 1260, "the right one centered on the main display")
assert(byKey("display-tidy").props.enabled == false, "already tidy")
assert(store.undo() and positions()["Acme 2"] == nil, "undo removes the whole drop")
H.drag("display-DP-2", "display-above-DP-1")
-- typing a position right after a drop is its own undo step (it doesn't merge into the drop)
local dropped = store.entryOps[#store.entryOps]
steps = #store.history
store.entryOp("output", { op = "set", index = dropped.index, field = "position", value = { x = 1, y = 2 } })
assert(#store.history == steps + 1, "a new step after the drop")
store.undo()
assert(json.encode(positions()) == json.encode(pos), "undo keeps the drop: " .. json.encode(positions()))

-- a second display on the same edge: the pair is centered on the main display
H.drag("display-HDMI-A-1", "display-above-DP-1")
pos = positions()
assert(pos["Acme 2"].x == 0 and pos["HDMI-A-1"].x == 1920 and pos["HDMI-A-1"].y == 0
       and pos["Acme 1"].x == 640 and pos["Acme 1"].y == 1080, "pair above: " .. json.encode(pos))
-- a corner zone: below, moved half a display to the right (its left edge on the main display's center line);
-- the display already above on the right half stays there
H.drag("display-DP-2", "display-below-end-DP-1")
pos = positions()
assert(pos["Acme 1"].x == 0 and pos["Acme 1"].y == 1080 and pos["HDMI-A-1"].x == 1280 and pos["HDMI-A-1"].y == 0
       and pos["Acme 2"].x == 1280 and pos["Acme 2"].y == 2520, "corner: " .. json.encode(pos))
-- dragging back and forth replaces the pending positions instead of adding to them
local opCount = #store.entryOps
H.drag("display-DP-2", "display-below-start-DP-1")
H.drag("display-DP-2", "display-below-end-DP-1")
assert(#store.entryOps <= opCount, "pending ops " .. #store.entryOps .. " > " .. opCount)
for _, where in ipairs({ "above-start", "above-end", "below-start", "below-end" }) do
  assert(byKey("display-" .. where .. "-DP-1"), "corner zone " .. where)
end
assert(H.walk(byKey("display-DP-1"), function(n) return n.props.name == "grip-horizontal" end), "a drag handle")
-- a display's own zones don't take it: Noctalia keeps the dragged tile in place and would pick its zone under
-- the pointer; every display drags as its own type and a tile's zones accept the other displays' types only
local ownType = byKey("display-DP-1").props.dragType
local ownAccepts = byKey("display-above-DP-1").props.accepts
assert(#ownAccepts == 2, "the two other displays: " .. table.concat(ownAccepts, ","))
for _, kind in ipairs(ownAccepts) do assert(kind ~= ownType, "own zones refuse the display") end
assert(not pcall(H.drag, "display-DP-1", "display-left-DP-1"), "no drop on itself")
assert(byKey("display-face-DP-1").props.fill:find("/", 1, true), "a see-through face (the dragged copy too)")

-- the default display: only its entry focuses at startup, and it is XWayland's primary output
local function focused()
  local names = {}
  for _, item in ipairs(store.entryItems("output")) do
    if item.values.focus_at_startup == true then table.insert(names, item.name) end
  end
  return table.concat(names, ",")
end
local function star(id) return H.walk(byKey("display-star-" .. id), function(n) return n.kind == "glyph" end) end
local function clickStar(id) byKey("display-star-" .. id).props.onClick(); flushReads() end
for _, id in ipairs({ "DP-1", "DP-2", "HDMI-A-1" }) do
  assert(star(id).props.name == "star" and star(id).props.color == "on_surface_variant", "grey stars: no default")
end
steps = #store.history
clickStar("DP-2")
assert(focused() == "Acme 2" and store.value("general.xwayland_primary_output") == "Acme 2", focused())
-- the star is one undo step: its entry and XWayland's primary output together
assert(#store.history == steps + 1, "one undo step for the star")
store.undo()
assert(focused() == "" and (store.value("general.xwayland_primary_output") or "") == "", "undo clears both")
H.goHome()
clickText("Outputs")
clickStar("DP-2")
assert(star("DP-2").props.name == "star-filled" and star("DP-2").props.color == "primary", "a filled star")
assert(star("DP-1").props.name == "star" and star("HDMI-A-1").props.name == "star", "grey stars on the others")
assert(byKey("display-face-DP-2").props.border == "primary", "the default tile is outlined")
clickStar("DP-1")
assert(focused() == "Acme 1" and store.value("general.xwayland_primary_output") == "Acme 1", "moved: " .. focused())
clickStar("DP-1")  -- the default's star again clears it
assert(focused() == "" and (store.value("general.xwayland_primary_output") or "") == "", "no default")

-- a name for the overview, set on the display's page
byKey("display-DP-1").props.onClick()
flushReads()
H.input("^label%-output%-1:").props.onChange("Desk")
H.goHome()
clickText("Outputs")
assert(H.walk(byKey("display-tile-DP-1"), function(n) return n.props.text == "Desk" end), "the tile shows the name")

-- a disabled display leaves the canvas
store.entryOp("output", { op = "set", index = 2, field = "enabled", value = false })
H.goHome()
clickText("Outputs")
assert(not byKey("display-HDMI-A-1") and byKey("display-off-HDMI-A-1"), "off displays are listed instead")
assert(not H.byKey("filter-Outputs-box") and not pcall(H.input, "^new%-output:"), "no entry list or Add box")

-- an entry for an output that isn't connected stays reachable, with a text box for the mode
store.entryOp("output", { op = "add", name = "DP-9" })
H.goHome()
clickText("Outputs")
assert(hasText("Not connected"), screen())
clickText("DP-9")
assert(hasText("DP-9") and not pcall(select, ":resolution$"), "no dropdowns for a disconnected output")
assert(H.input("mode"), "mode text box")

-- Try: display edits are saved at once and kept only when confirmed in time; otherwise the backup comes back
-- and the edits are pending again
store.discardAll()
H.goHome()
clickText("Outputs")
assert(byKey("display-try").props.enabled == false, "nothing to try")
H.drag("display-DP-2", "display-above-DP-1")
local tried = positions()["Acme 2"]
assert(byKey("display-try").props.enabled, "display edits can be tried")
local state = json.decode(H.fixtures.state)
replies.save = function(request)
  assert(request.validate == true, "a try is validated")
  assert(request.trial == 15, "the helper arms its own rollback before writing")
  return true, json.encode({ saved = true, state = state, backup = "/b/config.toml.9.bak", trial = "t1",
                             validation = { ran = true, valid = true, diagnostics = {} } })
end
replies.restore = function(request)
  assert(request.snapshot == "/b/config.toml.9.bak" and json.encode(request.revision) == json.encode(state.revision),
         "restores the try's backup at the tried revision")
  assert(request.trial == "t1", "going back claims the trial, so the watcher doesn't restore again")
  return true, json.encode({ state = state, backups = { backups = {} } })
end
H.hold("wait")
clickText("Try")
flushReads()
assert(hasText("Keep these display settings? Going back in 15 seconds."), screen())
assert(#store.entryOps == 0, "saved")
H.release("wait")
assert(hasText("Keep these display settings? Going back in 14 seconds."), screen())
for _ = 1, 14 do H.release("wait") end
local AGAIN = " Your display edits are unsaved again."
assert(H.lastCall("restore") and hasText("No answer within 15 seconds. The previous display settings are back." .. AGAIN),
       screen())
assert(not byKey("display-try-card") and positions()["Acme 2"].y == tried.y, "the tried edits are pending again")
assert(store.undo() and positions()["Acme 2"] == nil, "and undo as one step")
-- Keep
H.drag("display-DP-2", "display-above-DP-1")
clickText("Try")
flushReads()
replies["trial-end"] = function(request)
  assert(request.trial == "t1", "keep ends this trial")
  return true, json.encode({ ended = true })
end
clickText("Keep")
assert(H.lastCall("trial-end") and hasText("Display settings kept.") and #store.entryOps == 0, screen())
assert(H.release("wait") == 1 and not byKey("display-try-card"), "the countdown stops")
-- tried but not read back: no Keep without the revision, and it says the helper's watcher still goes back
local trySave = replies.save
replies.save = function()
  return true, json.encode({ saved = true, backup = "/b/config.toml.9.bak", trial = "t1",
                             validation = { ran = true, valid = true, diagnostics = {} } })
end
H.drag("display-DP-2", "display-above-DP-1")
clickText("Try")
flushReads()
assert(hasText("Tried, but the file could not be read back, so Keep isn't possible: the previous display "
               .. "settings come back in about 30 seconds.") and not byKey("display-try-card"), screen())
replies.save = trySave
store.discardAll()
H.goHome()
clickText("Outputs")
-- Go back; while a Try runs its card shows on every page and Save waits
H.drag("display-DP-2", "display-above-DP-1")
clickText("Try")
flushReads()
H.goHome()
assert(byKey("display-try-card"), "Keep and Go back stay reachable from Home: " .. screen())
store.setField("appearance.border_width", 7)
replies.preview = function()
  return true, json.encode({ summary = {}, sections = {}, changed = true, validation = { ran = false } })
end
entry.onKey("ctrl+s", true)
flushReads()
replies.preview = nil
assert(not H.find("button", function(n) return n.props.key == "review-save" or n.props.text == "Save" end).props.enabled,
       "no save while a Try runs: " .. screen())
store.revertField("appearance.border_width")
H.goHome()
clickText("Go back")
flushReads()
assert(hasText("Went back. The previous display settings are back." .. AGAIN) and #store.entryOps > 0, screen())
H.release("wait", true)
-- Keep after the watcher already went back: the edits come back too
H.hold("wait")
clickText("Outputs")
clickText("Try")
flushReads()
replies["trial-end"] = function()
  return true, json.encode({ ended = false, message = "The previous display settings were already restored." })
end
clickText("Keep")
flushReads()
assert(hasText("Too late: The previous display settings were already restored." .. AGAIN) and #store.entryOps > 0,
       screen())
H.release("wait", true)
-- Go back after the watcher went back: trial_over, not an error
H.hold("wait")
clickText("Try")
flushReads()
local restoreReply = replies.restore
replies.restore = function() return false, "The previous display settings were already restored.", "trial_over" end
clickText("Go back")
flushReads()
replies.restore = restoreReply
assert(hasText("The previous display settings were already restored." .. AGAIN) and #store.entryOps > 0, screen())
H.release("wait", true)
-- the panel closes while the try is being saved: the answer still starts the countdown, which goes back and
-- queues the edits again (the store outlives the panel)
H.hold("save")
H.hold("wait")
clickText("Try")
entry.onClose()
local closedAt = #H.calls
H.release("save", true)
local ticking = false
for i = closedAt + 1, #H.calls do ticking = ticking or H.calls[i].command == "wait" end
assert(ticking, "the countdown starts although the panel is closed")
for _ = 1, 15 do H.release("wait") end
flushReads()
assert(H.notifications[#H.notifications] == "No answer within 15 seconds. The previous display settings are back."
       .. AGAIN, tostring(H.notifications[#H.notifications]))
assert(#store.entryOps > 0, "the edits are pending when the panel opens again")
H.release("wait", true)
entry.onOpen()
flushReads()
store.discardAll()

-- Noctalia runs at most 8 commands per plugin: reopening the panel on Outputs keeps one live poll, not one per
-- reopen (they piled up until every helper call failed); a poll answered while closed doesn't ask again
H.goHome()
clickText("Outputs")
assert(#H.liveWaits == 1, "Outputs waits for display changes")
for _ = 1, 8 do
  entry.onClose()
  entry.onOpen()
  flushReads()
end
assert(#H.liveWaits == 1, "one live poll after reopening: " .. #H.liveWaits)
assert(not hasText("Could not start"), screen())
entry.onClose()
assert(H.liveChange(nil) == 1 and #H.liveWaits == 0, "a poll answered while closed doesn't ask again")
entry.onOpen()
flushReads()
assert(#H.liveWaits == 1, "the page polls again once it is shown")
H.liveChange(nil)

print("outputs ok")
