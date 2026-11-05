-- ReaCue : lance le programme ReaCue (Python) depuis REAPER, sans Claude ni internet.
-- Code commun aux actions « ReaCue - Préparer le morceau » et « ReaCue - Republier le prompteur ».
-- Le pont ReaCue_Bridge.lua doit tourner (il est lancé au démarrage de REAPER).
--
-- Dossier d'installation de ReaCue (là où se trouvent .venv et reacue_mcp), dans l'ordre :
--   1. ExtState "ReaCue"/"install_dir" (réglage manuel, persistant) ;
--   2. <ressources REAPER>/ReaCueMCP/reacue_install.txt (écrit par l'installateur) ;
--   3. dossier parent de ce script s'il contient reacue_mcp (script lancé depuis <installation>/reaper) ;
--   4. ~/Documents/reacue-mcp (anciennes installations macOS).
--
-- Lancement en arrière-plan :
--   macOS / Linux : os.execute("cd … && nohup <python> -m reacue_mcp.cli … &") (comme avant) ;
--   Windows       : reaper.ExecProcess(<pythonw.exe> <reacue_cli.py> …, -1) : -1 = ne pas attendre.
--                   ExecProcess lance le programme directement (pas de cmd.exe, pas de fenêtre console
--                   avec pythonw.exe) et reçoit la ligne de commande en UTF-8 : les chemins avec espaces
--                   ou accents passent, contrairement à os.execute (page de code ANSI de cmd.exe).

local M = {}
local SEP = package.config:sub(1, 1)
local RES_DIR = reaper.GetResourcePath()
local DIR = RES_DIR .. SEP .. "ReaCueMCP"
local STATUS = DIR .. SEP .. "cli_status.json"
local HEARTBEAT = DIR .. SEP .. "heartbeat.txt"
local SETTINGS = DIR .. SEP .. "reacue_settings.json"
local INSTALL_TXT = DIR .. SEP .. "reacue_install.txt"
local TITLE = "ReaCue"

local function is_windows()
  local os_name = reaper.GetOS and reaper.GetOS() or ""
  return os_name:match("^Win") ~= nil or SEP == "\\"
end
M.is_windows = is_windows

local function read(path)
  local f = io.open(path, "rb"); if not f then return nil end
  local s = f:read("*a"); f:close(); return s
end

local function exists(path) local f = io.open(path, "rb"); if f then f:close() return true end return false end

-- JSON : lecture d'un champ chaîne ou nombre (fichiers écrits par Python json.dumps) ------------
local function utf8_char(c)
  if c < 0x80 then return string.char(c) end
  if c < 0x800 then return string.char(0xC0 | (c >> 6), 0x80 | (c & 0x3F)) end
  if c < 0x10000 then return string.char(0xE0 | (c >> 12), 0x80 | ((c >> 6) & 0x3F), 0x80 | (c & 0x3F)) end
  return string.char(0xF0 | (c >> 18), 0x80 | ((c >> 12) & 0x3F), 0x80 | ((c >> 6) & 0x3F), 0x80 | (c & 0x3F))
end

-- décode la chaîne JSON qui commence au guillemet d'indice i ; renvoie (valeur, indice après)
local function json_string(s, i)
  local out, j, n = {}, i + 1, #s
  local esc = { n = "\n", r = "\r", t = "\t", b = "\b", f = "\f", ['"'] = '"', ["\\"] = "\\", ["/"] = "/" }
  while j <= n do
    local c = s:sub(j, j)
    if c == '"' then return table.concat(out), j + 1 end
    if c == "\\" then
      local e = s:sub(j + 1, j + 1)
      if e == "u" then
        local cp = tonumber(s:sub(j + 2, j + 5), 16) or 63
        j = j + 6
        if cp >= 0xD800 and cp <= 0xDBFF and s:sub(j, j + 1) == "\\u" then   -- paire de substitution
          local lo = tonumber(s:sub(j + 2, j + 5), 16)
          if lo and lo >= 0xDC00 and lo <= 0xDFFF then
            cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
            j = j + 6
          end
        end
        out[#out + 1] = utf8_char(cp)
      else
        out[#out + 1] = esc[e] or e
        j = j + 2
      end
    else
      out[#out + 1] = c
      j = j + 1
    end
  end
  return nil
end

-- valeur du champ `key` (premier niveau) : chaîne, nombre, booléen ; nil si absent
local function jfield(s, key)
  if not s then return nil end
  local pat = '"' .. key:gsub("%p", "%%%0") .. '"%s*:%s*()'
  local p = s:match(pat)
  if not p then return nil end
  local c = s:sub(p, p)
  if c == '"' then return (json_string(s, p)) end
  local num = s:match("^%-?%d+%.?%d*[eE]?[%+%-]?%d*", p)
  if num and num ~= "" then return tonumber(num) end
  if s:sub(p, p + 3) == "true" then return true end
  if s:sub(p, p + 4) == "false" then return false end
  return nil
end
M.jfield = jfield

-- JSON complet (réglages, setlists) : décodage et encodage ---------------------------------
-- Les tableaux JSON gardent la marque « array » (même vides) pour être réécrits comme tableaux.
local ARRAY = { __jsontype = "array" }
function M.json_array(t) return setmetatable(t or {}, ARRAY) end
function M.is_array(t)
  if type(t) ~= "table" then return false end
  if getmetatable(t) == ARRAY then return true end
  if next(t) == nil then return false end
  local n = 0
  for k in pairs(t) do
    if type(k) ~= "number" or k < 1 or k % 1 ~= 0 then return false end
    n = n + 1
  end
  return n == #t
end

function M.json_decode(s)
  if type(s) ~= "string" then return nil end
  local i = 1
  local function ws() i = s:find("[^ \t\r\n]", i) or (#s + 1) end
  local value
  local function obj()
    local t = {}
    i = i + 1; ws()
    if s:sub(i, i) == "}" then i = i + 1 return t end
    while true do
      ws()
      if s:sub(i, i) ~= '"' then error("json: key") end
      local k, j = json_string(s, i)
      i = j; ws()
      if s:sub(i, i) ~= ":" then error("json: colon") end
      i = i + 1
      t[k] = value()
      ws()
      local c = s:sub(i, i)
      i = i + 1
      if c == "}" then return t end
      if c ~= "," then error("json: object") end
    end
  end
  local function arr()
    local t = M.json_array({})
    i = i + 1; ws()
    if s:sub(i, i) == "]" then i = i + 1 return t end
    while true do
      t[#t + 1] = value()
      ws()
      local c = s:sub(i, i)
      i = i + 1
      if c == "]" then return t end
      if c ~= "," then error("json: array") end
    end
  end
  value = function()
    ws()
    local c = s:sub(i, i)
    if c == "{" then return obj() end
    if c == "[" then return arr() end
    if c == '"' then local v, j = json_string(s, i); i = j; return v end
    if s:sub(i, i + 3) == "true" then i = i + 4 return true end
    if s:sub(i, i + 4) == "false" then i = i + 5 return false end
    if s:sub(i, i + 3) == "null" then i = i + 4 return nil end
    local num = s:match("^%-?%d+%.?%d*[eE]?[%+%-]?%d*", i)
    if num and num ~= "" then i = i + #num; return tonumber(num) end
    error("json: value at " .. i)
  end
  local ok, v = pcall(value)
  if ok then ws(); if i > #s then return v end end
  return nil
end

local function json_str_enc(v)
  -- JSON échappe les contrôles ASCII, pas les octets de continuation des caractères UTF-8.
  return '"' .. v:gsub('[%z\1-\31"\\]', function(c)
    local map = { ['"'] = '\\"', ['\\'] = '\\\\', ["\n"] = "\\n", ["\r"] = "\\r", ["\t"] = "\\t" }
    return map[c] or string.format("\\u%04x", c:byte())
  end) .. '"'
end

-- order : liste de clés à écrire en premier (les autres suivent, triées)
function M.json_encode(v, indent, order, depth)
  depth = depth or 0
  local t = type(v)
  if v == nil then return "null" end
  if t == "boolean" then return v and "true" or "false" end
  if t == "number" then
    if v ~= v or v == math.huge or v == -math.huge then return "null" end
    if math.type and math.type(v) == "integer" then return tostring(v) end
    if v % 1 == 0 and math.abs(v) < 1e15 then return string.format("%d", v) end
    return string.format("%.10g", v)
  end
  if t == "string" then return json_str_enc(v) end
  if t ~= "table" then return json_str_enc(tostring(v)) end
  local nl = indent and ("\n" .. string.rep(indent, depth + 1)) or ""
  local nl0 = indent and ("\n" .. string.rep(indent, depth)) or ""
  local sp = indent and " " or ""
  if M.is_array(v) or (getmetatable(v) == ARRAY) then
    if #v == 0 then return "[]" end
    local out = {}
    for k = 1, #v do out[k] = nl .. M.json_encode(v[k], indent, nil, depth + 1) end
    return "[" .. table.concat(out, ",") .. nl0 .. "]"
  end
  local keys, seen = {}, {}
  for _, k in ipairs(order or {}) do if v[k] ~= nil then keys[#keys + 1] = k; seen[k] = true end end
  local rest = {}
  for k in pairs(v) do if not seen[k] then rest[#rest + 1] = tostring(k) end end
  table.sort(rest)
  for _, k in ipairs(rest) do keys[#keys + 1] = k end
  if #keys == 0 then return "{}" end
  local out = {}
  for n, k in ipairs(keys) do out[n] = nl .. json_str_enc(k) .. ":" .. sp .. M.json_encode(v[k], indent, nil, depth + 1) end
  return "{" .. table.concat(out, ",") .. nl0 .. "}"
end

-- Remplacement atomique sur POSIX ; sauvegarde/restauration sur Windows si le remplacement est refusé.
function M.write_atomic(path, text)
  local tmp = path .. ".tmp"
  local f = io.open(tmp, "wb"); if not f then return false end
  local wrote = f:write(text)
  local closed = f:close()
  if not wrote or not closed then os.remove(tmp); return false end
  if os.rename(tmp, path) then return true end -- remplace sans retirer l'ancien fichier sur macOS/Linux
  if not is_windows() or not exists(path) then os.remove(tmp); return false end
  -- Le CRT Windows peut refuser rename si la destination existe. Ne jamais écraser une sauvegarde
  -- non restaurée d'un échec précédent ; si la seconde opération échoue, remettre l'ancien fichier.
  local backup = path .. ".previous"
  if exists(backup) or not os.rename(path, backup) then os.remove(tmp); return false end
  if os.rename(tmp, path) then os.remove(backup); return true end
  os.rename(backup, path) -- en cas d'échec de restauration, la sauvegarde reste récupérable
  os.remove(tmp)
  return false
end

M.read = read
M.exists = exists
M.SETTINGS = SETTINGS
M.STATUS = STATUS
M.DIR = DIR

-- Langue ------------------------------------------------------------------------
local TXT = {
  fr = {
    prepare = "Préparation du morceau en cours",
    publish = "Mise à jour du prompteur",
    not_found = "Programme ReaCue introuvable :\n%s\n\nRelance l'installation de ReaCue, ou indique son dossier avec :\nreaper.SetExtState(\"ReaCue\", \"install_dir\", \"<dossier>\", true)",
    no_bridge = "Le pont ReaCue ne tourne pas dans REAPER.\nLance l'action « ReaCue_Bridge.lua » (ou redémarre REAPER) puis recommence.",
    busy = "Une préparation est déjà en cours. Attends qu'elle se termine.",
    launch_failed = "Impossible de lancer ReaCue :\n%s",
    done = "Terminé.", error = "Erreur.",
    timeout = "Pas de réponse après 15 min : voir %s",
    hint = "%d s  ·  tu peux fermer cette fenêtre, le résultat s'affichera à la fin",
  },
  en = {
    prepare = "Preparing the song",
    publish = "Updating the prompter",
    not_found = "ReaCue program not found:\n%s\n\nRun the ReaCue installer again, or set its folder with:\nreaper.SetExtState(\"ReaCue\", \"install_dir\", \"<folder>\", true)",
    no_bridge = "The ReaCue bridge is not running in REAPER.\nRun the “ReaCue_Bridge.lua” action (or restart REAPER) and try again.",
    busy = "A preparation is already running. Wait until it finishes.",
    launch_failed = "Could not start ReaCue:\n%s",
    done = "Done.", error = "Error.",
    timeout = "No answer after 15 min: see %s",
    hint = "%d s  ·  you can close this window, the result will show at the end",
  },
}

function M.lang()
  local l = jfield(read(SETTINGS), "language")
  l = type(l) == "string" and l:sub(1, 2):lower() or "fr"
  return TXT[l] and l or "fr"
end

function M.tr(key)
  return TXT[M.lang()][key] or TXT.fr[key]
end

-- Shared lock protects ReaCue edits/calculations; native REAPER transport remains usable.
function M.show_locked()
  local raw = read(DIR .. SEP .. "show_lock.json")
  if raw == nil then return false end
  local data = M.json_decode(raw)
  return type(data) ~= "table" or data.locked ~= false
end
function M.lock_message()
  return M.lang() == "fr" and "Concert verrouillé. Déverrouille les modifications dans l’onglet Scène."
    or "Show locked. Unlock editing in the Stage tab."
end
function M.project_file()
  if not reaper.EnumProjects then return "" end
  local _, path = reaper.EnumProjects(-1, "")
  return path or ""
end
-- nil means unknown: it never permits a duplicate worker.
function M.pid_alive(pid)
  pid = tonumber(pid)
  if not pid or pid <= 0 or pid % 1 ~= 0 or not reaper.ExecProcess then return nil end
  local cmd = is_windows() and ('tasklist /FI "PID eq ' .. tostring(pid) .. '" /NH')
    or ('/bin/kill -0 ' .. tostring(pid))
  local ok, out = pcall(reaper.ExecProcess, cmd, 500)
  if not ok or type(out) ~= "string" then return nil end
  local code = tonumber(out:match("^(%-?%d+)"))
  if is_windows() then
    if code ~= 0 then return nil end
    if out:find("aucun", 1, true) or out:find("No tasks", 1, true) then return false end
    return out:find(tostring(pid), 1, true) and true or nil
  end
  if code == 0 then return true end
  if code == 1 and out:find("No such process", 1, true) then return false end
  return nil
end
function M.job_active(data)
  if type(data) ~= "table" or data.state ~= "running" then return false end
  if data.launching and not data.pid then return os.time() - (data.time or 0) < 15 end
  return M.pid_alive(data.pid) ~= false
end
function M.active_job()
  local d = M.json_decode(read(STATUS))
  if M.job_active(d) then return d end
  -- Concert extras can continue after the usable result was published.
  if d and d.id and tostring(d.id):match("^[%w_-]+$") then
    local record = M.json_decode(read(DIR .. SEP .. "jobs" .. SEP .. d.id .. ".json"))
    if M.job_active(record) then return record end
  end
end

-- Installation --------------------------------------------------------------------
local function trim(s) return (s or ""):gsub("^%s+", ""):gsub("%s+$", "") end

function M.install_dir(script_dir)
  local d = reaper.GetExtState("ReaCue", "install_dir")
  if d ~= "" then return d end
  local t = trim(read(INSTALL_TXT))
  if t ~= "" then return (t:gsub("[/\\]+$", "")) end
  if script_dir then
    local parent = script_dir:match("^(.*)[/\\][^/\\]+$")
    if parent and exists(parent .. SEP .. "reacue_mcp" .. SEP .. "cli.py") then return parent end
  end
  return (os.getenv("HOME") or os.getenv("USERPROFILE") or "") .. SEP .. "Documents" .. SEP .. "reacue-mcp"
end

function M.python(dir, windows)
  if windows then
    local pyw = dir .. "\\.venv\\Scripts\\pythonw.exe"
    if exists(pyw) then return pyw end
    return dir .. "\\.venv\\Scripts\\python.exe"
  end
  return dir .. "/.venv/bin/python"
end

-- analyse de structure SongFormer (composant optionnel : Install ReaCue Structure) installée ?
function M.structure_installed(dir, windows)
  if windows == nil then windows = is_windows() end
  local py = windows and (dir .. "\\.venv-structure\\Scripts\\python.exe") or (dir .. "/.venv-structure/bin/python")
  local sep = windows and "\\" or "/"
  return exists(py) and exists(dir .. sep .. "reacue_structure.py")
end

-- guillemets shell POSIX : 'a'\''b'
function M.shq(s) return "'" .. tostring(s):gsub("'", "'\\''") .. "'" end

-- ligne de commande Windows (règles de CommandLineToArgvW ; un chemin Windows ne contient pas de ")
function M.winq(s)
  s = tostring(s)
  if s:find('[%s"]') or s == "" then
    s = s:gsub("(\\*)$", "%1%1")          -- barres obliques inverses finales doublées avant le "
    return '"' .. s .. '"'
  end
  return s
end

function M.command(cmd, dir, py, windows, log)
  if windows then
    return table.concat({ M.winq(py), M.winq(dir .. "\\reacue_cli.py"), cmd, "--resource-dir", M.winq(RES_DIR) }, " ")
  end
  return string.format("cd %s && nohup %s -m reacue_mcp.cli %s --resource-dir %s >> %s 2>&1 &",
    M.shq(dir), M.shq(py), cmd, M.shq(RES_DIR), M.shq(log))
end

local function bridge_alive()
  local s = read(HEARTBEAT); if not s then return false end
  local t = tonumber(s:match("[%d%.]+"))
  if t and math.abs(os.time() - t) < 15 then return true end
  -- heartbeat sans horodatage lisible : on se fie à sa présence
  return t == nil
end

M.bridge_alive = bridge_alive
-- durée maximale d'une commande (analyse de structure SongFormer comprise, sur CPU lent)
M.TIMEOUT = 2400

-- lance la CLI en arrière-plan sans fenêtre (fenêtre ReaCue) : renvoie true, ou false + message
function M.start(cmd, script_dir, need_bridge)
  local windows = is_windows()
  local dir = M.install_dir(script_dir)
  local py = M.python(dir, windows)
  if not exists(py) then return false, string.format(M.tr("not_found"), py) end
  if need_bridge ~= false and not bridge_alive() then return false, M.tr("no_bridge") end
  if M.show_locked() then return false, M.lock_message() end
  local current = M.active_job()
  local project = M.project_file()
  if current then
    if project ~= "" and current.project == project and current.launch_command == cmd then
      return true, nil, current -- resume monitoring, never spawn the same job twice
    end
    return false, M.tr("busy")
  end
  local id = tostring(os.time()) .. "-" .. tostring(math.floor(reaper.time_precise() * 1000000))
  local pending = {id=id, cmd=cmd:match("^(%S+)"), launch_command=cmd, project=project,
    state="running", launching=true, time=os.time(), started=os.time()}
  reaper.RecursiveCreateDirectory(DIR, 0)
  if not M.write_atomic(STATUS, M.json_encode(pending)) then return false, M.tr("error") end
  local quote = windows and M.winq or M.shq
  local full = cmd .. " --job-id " .. quote(id) .. " --origin-project " .. quote(project)
    .. " --launch-command " .. quote(cmd)
  local log = DIR .. SEP .. "cli.log"
  local line = M.command(full, dir, py, windows, log)
  if windows then
    if reaper.ExecProcess(line, -1) == nil then return false, string.format(M.tr("launch_failed"), line) end
  else
    os.execute(line)
  end
  return true, nil, pending
end

-- état de la dernière commande : state ("running" | "done" | "error" | nil), message, cmd
function M.status(id)
  local s
  if id and tostring(id):match("^[%w_-]+$") then s=read(DIR .. SEP .. "jobs" .. SEP .. id .. ".json") end
  s = s or read(STATUS)
  if not s then return nil end
  return jfield(s, "state"), jfield(s, "message"), jfield(s, "cmd"), jfield(s, "step"), jfield(s, "prompter_published"), M.json_decode(s)
end

function M.run(cmd, label, script_dir)
  label = (label and label ~= "") and label or M.tr(cmd)
  local ok, err = M.start(cmd, script_dir)
  if not ok then reaper.ShowMessageBox(err, TITLE, 0) return end
  local log = DIR .. SEP .. "cli.log"
  local t0 = reaper.time_precise()
  local spin = { "|", "/", "-", "\\" }
  local win = true
  gfx.init(TITLE, 480, 110)
  local function finish(msg)
    if win then gfx.quit() end
    reaper.ShowMessageBox(msg, TITLE, 0)
  end
  local function loop()
    local el = reaper.time_precise() - t0
    local state, msg, _, step = M.status()
    if state == "done" or state == "error" then
      finish(msg or (state == "done" and M.tr("done") or M.tr("error")))
      return
    end
    if step and step ~= "" then label = step end
    if el > M.TIMEOUT then finish(string.format(M.tr("timeout"), log)) return end
    if win then
      if gfx.getchar() < 0 then win = false else
        gfx.set(0.08, 0.09, 0.11, 1); gfx.rect(0, 0, gfx.w, gfx.h, 1)
        gfx.set(1, 1, 1, 1); gfx.setfont(1, "Arial", 20)
        gfx.x, gfx.y = 20, 22; gfx.drawstr(label .. "  " .. spin[(math.floor(el * 4) % 4) + 1])
        gfx.set(0.6, 0.65, 0.72, 1); gfx.setfont(1, "Arial", 15)
        gfx.x, gfx.y = 20, 62
        gfx.drawstr(string.format(M.tr("hint"), math.floor(el)))
        gfx.update()
      end
    end
    reaper.defer(loop)
  end
  loop()
end

return M
