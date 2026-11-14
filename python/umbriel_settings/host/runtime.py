"""Lua 5.4 runtime (lupa) that runs the shared Luau UI like Noctalia does."""

import locale
import sys
import traceback

from lupa import lua54

UI_KINDS = (
    "column", "row", "scroll", "label", "fillLabel", "markdown", "glyph", "image", "box", "separator",
    "spacer", "progress", "button", "toggle", "slider", "colorPicker", "select", "input",
)

# Noctalia rules: require("./x.luau") is relative to the requiring file, each module gets a private
# global table (reads fall through to the shared globals) and is loaded once per entry.
BOOTSTRAP = r"""
local kinds = ...
ui = {}
for _, kind in ipairs(kinds) do
  ui[kind] = function(props, children)
    return { kind = kind, props = props or {}, children = children or {} }
  end
end

local loaded = {}
local function normalize(path)
  repeat local before = path; path = path:gsub("/%./", "/") until path == before
  repeat local before = path; path = path:gsub("/[^/]+/%.%./", "/", 1) until path == before
  return path
end

local function makeRequire(dir)
  return function(path)
    if type(path) ~= "string" or not path:match("^%.%.?/") or not path:match("%.luau$") then
      error("require path must be relative and end in .luau", 2)
    end
    local full = normalize(dir .. "/" .. path)
    if loaded[full] == nil then
      local env = setmetatable({}, { __index = _G })
      env.require = makeRequire(full:match("^(.*)/[^/]+$"))
      local chunk = assert(loadfile(full, "t", env))
      local value = chunk()
      if value == nil then error("module " .. full .. " returned nil", 2) end
      loaded[full] = value
    end
    return loaded[full]
  end
end

return function(path, dir, app)
  local env = setmetatable({}, { __index = _G })
  env.require = makeRequire(dir)
  env.APP = app
  assert(loadfile(path, "t", env))()
  return env
end
"""


class LuaHost:
    """Owns the Lua state, the entry script's globals and the callbacks of the last rendered tree."""

    def __init__(self, ui_dir, on_render=None, on_error=None):
        # Lua formats and parses numbers with the C locale's decimal point; Qt switches LC_NUMERIC to
        # the user's locale (e.g. "0,75"), which would break string.format and tonumber in the shared UI.
        locale.setlocale(locale.LC_NUMERIC, "C")
        self.ui_dir = ui_dir
        self.lua = lua54.LuaRuntime(unpack_returned_tuples=True)
        self.on_render = on_render or (lambda tree: None)
        self.on_error = on_error or self._print_error
        self.entry = None
        self.callbacks = {}
        self.tree = None
        self.errors = []
        self._load_entry = self.lua.execute(BOOTSTRAP, self.to_lua(list(UI_KINDS)))

    # ------------------------------------------------------------------ conversion
    def is_table(self, value):
        return lua54.lua_type(value) == "table"

    def to_py(self, value):
        """Lua value → plain Python (tables with keys 1..n become lists; an empty table becomes [])."""
        kind = lua54.lua_type(value)
        if kind == "table":
            keys = list(value.keys())
            if all(isinstance(k, int) for k in keys) and sorted(keys) == list(range(1, len(keys) + 1)):
                return [self.to_py(value[i]) for i in range(1, len(keys) + 1)]
            return {str(k): self.to_py(value[k]) for k in keys}
        if kind == "function":
            return None
        return value

    def to_lua(self, value):
        """Plain Python → Lua (None entries in dicts are dropped, like JSON null in Noctalia)."""
        if isinstance(value, dict):
            table = self.lua.table()
            for key, item in value.items():
                if item is not None:
                    table[key] = self.to_lua(item)
            return table
        if isinstance(value, (list, tuple)):
            table = self.lua.table()
            for index, item in enumerate(value, start=1):
                table[index] = self.to_lua(item)
            return table
        return value

    # ------------------------------------------------------------------ entry
    def start(self, entry_name="app.luau", app_options=None, globals_=None):
        """Install API globals (noctalia, panel, ...) and run the entry script."""
        g = self.lua.globals()
        for name, value in (globals_ or {}).items():
            g[name] = value
        self.entry = self._load_entry(f"{self.ui_dir}/{entry_name}", self.ui_dir, self.to_lua(app_options or {}))
        return self.entry

    def call(self, name, *args):
        """Call a global function of the entry script (onOpen, onKey, ...); errors are reported, not raised."""
        function = self.entry[name] if self.entry is not None else None
        if function is None:
            return None
        return self.guard(function, *args)

    def guard(self, function, *args):
        try:
            return function(*args)
        except Exception as error:  # Lua errors and Python errors raised inside API calls
            self.errors.append(str(error))
            self.on_error(error)
            return None

    def _print_error(self, error):
        print(f"umbriel-settings UI error: {error}", file=sys.stderr)
        if not isinstance(error, lua54.LuaError):
            traceback.print_exception(error)

    # ------------------------------------------------------------------ rendering
    def render(self, tree):
        """panel.render(tree): convert to plain data; Lua functions become callback ids."""
        self.callbacks = {}
        self.tree = self._convert_node(tree)
        self.on_render(self.tree)

    def _convert_node(self, node):
        if not self.is_table(node):
            return None
        props = {}
        raw_props = node["props"]
        if self.is_table(raw_props):
            for key in list(raw_props.keys()):
                props[str(key)] = self._convert_prop(raw_props[key])
        children = []
        raw_children = node["children"]
        if self.is_table(raw_children):
            for index in range(1, len(raw_children) + 1):
                child = self._convert_node(raw_children[index])
                if child is not None:
                    children.append(child)
        return {"kind": node["kind"], "props": props, "children": children}

    def _convert_prop(self, value):
        kind = lua54.lua_type(value)
        if kind == "function":
            callback_id = f"cb{len(self.callbacks) + 1}"
            self.callbacks[callback_id] = value
            return {"$callback": callback_id}
        if kind == "table":
            return self.to_py(value)
        return value

    def invoke(self, callback, *args):
        """Run a callback from the renderer: {"$callback": id} or the name of an entry global."""
        if isinstance(callback, dict) and "$callback" in callback:
            function = self.callbacks.get(callback["$callback"])
        elif isinstance(callback, str):
            function = self.entry[callback] if self.entry is not None else None
        else:
            function = None
        if function is None:
            return None
        return self.guard(function, *[as_callback_arg(arg) for arg in args])


def as_callback_arg(value):
    """Noctalia passes callback values as strings: "true"/"false", numbers as text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
