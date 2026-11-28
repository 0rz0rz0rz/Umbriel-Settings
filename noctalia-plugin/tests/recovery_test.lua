-- A config that doesn't load: Backups still restore it (the revision comes from the listing), and once it
-- loads, the config path box shows its path.
-- Usage: lua recovery_test.lua PLUGIN_DIR FIXTURE_DIR
local H = dofile((arg[0]:match("^(.*)/") or ".") .. "/harness.lua")
local entry = H.start("panel.luau")
local json, replies, fixtures = H.json, H.replies, H.fixtures
local flushReads, hasText, clickText, lastCall, screen = H.flushReads, H.hasText, H.clickText, H.lastCall, H.screen

local goodRead = replies.read
replies.read = function() return false, "/c/config.toml is not valid TOML: line 3" end
entry.onOpen()
flushReads()
assert(H.fullScreen():find("not valid TOML", 1, true), "the read error is shown: " .. screen())
local pathBox = H.input("^path:")
assert(pathBox and pathBox.props.value == "", "no path while nothing loaded")
local emptyKey = pathBox.props.key

replies.backups = function() return true, json.encode({ revision = { config = "abc" }, backups = {
  { path = "/b/config.toml.1.bak", name = "config.toml.1.bak", time = "2026-11-14 10:00:00", size = 2048 } } }) end
clickText("Backups")
assert(hasText("Restore"), screen())
replies.read = goodRead
replies.restore = function(request)
  assert(request.revision and request.revision.config == "abc", "the listing's revision is sent")
  return true, json.encode({ state = json.decode(fixtures.state), backups = { backups = {} } })
end
clickText("Restore")
clickText("Click again to restore")
assert(lastCall("restore"), "restore ran without a loaded config: " .. screen())
assert(H.fullScreen():find("Backup restored.", 1, true) or #H.notifications > 0, screen())

H.goHome()
flushReads()
local path = json.decode(fixtures.state).path
pathBox = H.input("^path:")
assert(pathBox and pathBox.props.value == path, "the path box shows the loaded config: " .. tostring(pathBox and pathBox.props.value))
-- Noctalia sets an input's text only when it creates it: a new key makes it take the loaded path
assert(pathBox.props.key ~= emptyKey, "the path box is recreated for the loaded path")
print("recovery ok")
