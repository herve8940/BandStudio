-- ReaCue : code commun du mode concert (fenêtre « ReaCue - Concert », Morceau suivant / précédent).
-- ReaCue: shared code of concert mode (“ReaCue - Concert” window, Next / Previous song).
-- Les données d'un concert sont dans <projet>.concert.lua (écrit par ReaCue, données pures).

local L = {}
local SEP = package.config:sub(1, 1)
local LIB_DIR = debug.getinfo(1, "S").source:match("^@?(.*[/\\])") or ""
local R = dofile(LIB_DIR .. "ReaCue_run.lua")       -- langue, réglages, dossier d'installation, lancement CLI
L.R = R
L.dir = LIB_DIR

-- textes (langue du réglage « language » de reacue_settings.json) -----------------------
local TXT = {
  fr = {
    title = "ReaCue - Concert",
    not_concert = "Ce projet n'est pas un concert ReaCue.\nOuvre-en un avec l'action « ReaCue - Concert ».",
    state = { play = "Lecture", pause = "Pause", stop = "Arrêt" },
    prev = "Précédent", home = "Début", play = "Lecture", pause = "Pause", stop = "Stop", next = "Suivant",
    again = "encore ?", count_in = "décompte", bar = "mesure %d / %d", rest = "reste %s",
    rest_k = "Reste", concert_k = "Concert", song_k = "Morceau",
    sections = "Sections", no_regions = "(pas de régions pour ce morceau)",
    next_song = "Ensuite : %d · %s · %s BPM · %s", last_song = "Dernier morceau du concert",
    rebuilding = "reconstruction… %d s", auto_stop = "arrêt auto actif",
    setlist = "Setlist", rebuild = "Reconstruire le concert",
    rebuild_q = "Reconstruire le concert à partir des projets des morceaux ?\n\nLes modifications faites directement dans le projet concert seront perdues.",
    not_found = "Programme ReaCue introuvable :\n%s", error = "Erreur",
    pin_title = "ReaCue - Code PIN de la Régie", pin_field = "Nouveau code (4 chiffres) :",
    pin_bad = "Le code doit faire exactement 4 chiffres.", pin_btn = "PIN %s",
    qr_title = "Prompteur des musiciens", qr_sub = "Scanner avec l'appareil photo du téléphone", close = "Fermer",
    no_ip = "Adresse IP de l'ordinateur introuvable.", no_ip2 = "Vérifie que l'ordinateur est connecté au Wi-Fi (ou au réseau),",
    no_ip3 = "puis clique à nouveau sur QR.", qr_fail = "QR code impossible : %s",
    same_wifi = "Même Wi-Fi que l'ordinateur", other_ip = "  ·  autre adresse : %s",
    pin_line = "Code PIN de la Régie : %s",
    no_web = "Interface web REAPER non trouvée : port 8080 supposé (Préférences › Control/OSC/web)",
    qr_missing = "ReaCue_qrcode.lua introuvable",
    phone = "téléphone : %s ✓", phone_badpin = "téléphone : code PIN incorrect",
    cmd = { toggle = "Lecture/Pause", play = "Lecture", pause = "Pause", stop = "Stop", prev = "Précédent",
      next = "Suivant", home = "Début", song = "Morceau", seek = "Section", reh = "Répétition", loop = "Boucle",
      loopoff = "Boucle off", rate = "Vitesse", mute = "Mute", solo = "Solo", hearall = "Tout entendre",
      loopsec = "Boucle section", ramp = "Rampe de vitesse", pitch = "Transposition", export = "Export audio",
      tctest = "Test timecode 10 s" },
    studio_line = "Studio (ordinateur, tablette) : %s",
    concert_n = "Concert %s / %s",
    none = "Aucun concert dans ce projet", building = "Construction du concert… %d s",
    open_one = "Ouvrir un concert (nouvel onglet) :", none_in = "Aucun concert dans %s",
    ask_claude = "Demande à Claude : « concert : morceau 1, morceau 2… »",
    n_songs = "%s  ·  %d morceaux", to_build = "Setlists à construire :", build = "Construire  %s",
    -- contrôle avant concert
    check = "Vérifier", recheck = "Revérifier", fix = "Corriger", check_title = "Contrôle avant concert",
    all_ready = "Tout est prêt", n_problems = "%d problème(s)", n_warnings = "%d point(s) à surveiller",
    ck = {
      media = "Fichiers audio", media_ok = "%d fichiers lisibles", media_bad = "%d illisible(s) ou hors ligne : %s",
      voice = "Annonces vocales", voice_ok = "%d annonces présentes", voice_bad = "%d annonce(s) manquante(s)", voice_none = "aucune piste d'annonces",
      fresh = "Concert à jour", fresh_ok = "construit le %s, aucun morceau modifié depuis",
      fresh_bad = "modifié(s) depuis la construction : %s", fresh_unknown = "concert construit avec une ancienne version : reconstruis-le une fois",
      fresh_missing = "projet introuvable : %s",
      songs = "Morceaux préparés", songs_ok = "%d morceaux avec structure et tempo",
      songs_bad = "à préparer puis enregistrer : %s",
      bridge = "Pont ReaCue", bridge_ok = "actif", bridge_bad = "ne répond pas : redémarre REAPER",
      web = "Interface web (prompteur)", web_ok = "active, port %d", web_bad = "introuvable : Préférences › Control/OSC/web",
      ip = "Adresse réseau", ip_ok = "%s", ip_bad = "aucune : connecte l'ordinateur au Wi-Fi du groupe",
      audio = "Carte son", audio_ok = "active · %s · %d sorties", audio_bad = "arrêtée : Préférences › Audio › Device",
      outs = "Sorties click et annonces", outs_ok = "%s", outs_bad = "%s", outs_master = "vers la sortie principale",
      outs_hw = "%s → sorties %d/%d", outs_missing = "%s → sortie %d absente (la carte en a %d)",
      outs_nowhere = "%s n'est envoyée nulle part", outs_muted = "%s est coupée (mute)", outs_none = "pas de piste CLICK",
      prompter = "Prompteur des téléphones", prompter_ok = "page et concert publiés", prompter_bad = "pas à jour : republier",
      regie = "Téléphones Régie", regie_ok = "vu il y a %d s", regie_none = "aucun téléphone en Régie pour l'instant",
      mix = "Stems coupés", mix_some = "%s", mix_none = "aucun : tous les stems sont joués", mix_all = "tous les stems sont coupés",
    },
    -- mode répétition
    reh = "Répétition", reh_on = "RÉPÉTITION", reh_loop = "boucle : %s", reh_loop_range = "boucle : %s → %s",
    reh_noloop = "touche une section pour la faire boucler (2e section = plage)",
    loop_off = "Boucle off", reh_exit = "Quitter", rate = "%d %%",
    auto_off = "arrêt auto coupé (répétition)",
    -- instruments (stems)
    instruments = "Instruments (stems)", hear_all = "Tout entendre", back_profile = "Profil",
    mix_none = "aucune piste d'instrument", solo_hint = "appui long = solo",
    mix_played = "joué", mix_cut = "coupé", mix_solo = "solo",
    live_title = "Joué en live", live_hint = "Coché = joué en vrai par le groupe : le stem est coupé",
    live_exc = "Exceptions par morceau", live_exc_hint = "clic : stem / live / profil",
    live_exc_stem = "stem", live_exc_live = "live", live_exc_def = "·",
    live_saved = "profil enregistré", live_nosetlist = "Setlist introuvable : reconstruis le concert.",
  },
  en = {
    title = "ReaCue - Concert",
    not_concert = "This project is not a ReaCue concert.\nOpen one with the “ReaCue - Concert” action.",
    state = { play = "Playing", pause = "Paused", stop = "Stopped" },
    prev = "Previous", home = "Start", play = "Play", pause = "Pause", stop = "Stop", next = "Next",
    again = "again?", count_in = "count-in", bar = "bar %d / %d", rest = "%s left",
    rest_k = "Left", concert_k = "Show", song_k = "Song",
    sections = "Sections", no_regions = "(no regions for this song)",
    next_song = "Next: %d · %s · %s BPM · %s", last_song = "Last song of the concert",
    rebuilding = "rebuilding… %d s", auto_stop = "auto stop on",
    setlist = "Setlist", rebuild = "Rebuild the concert",
    rebuild_q = "Rebuild the concert from the songs' projects?\n\nChanges made directly in the concert project will be lost.",
    not_found = "ReaCue program not found:\n%s", error = "Error",
    pin_title = "ReaCue - Stage control PIN code", pin_field = "New code (4 digits):",
    pin_bad = "The code must be exactly 4 digits.", pin_btn = "PIN %s",
    qr_title = "Musicians' prompter", qr_sub = "Scan with the phone's camera", close = "Close",
    no_ip = "Computer IP address not found.", no_ip2 = "Check that the computer is connected to the Wi-Fi (or network),",
    no_ip3 = "then click QR again.", qr_fail = "QR code failed: %s",
    same_wifi = "Same Wi-Fi as the computer", other_ip = "  ·  other address: %s",
    pin_line = "Stage control PIN code: %s",
    no_web = "REAPER web interface not found: port 8080 assumed (Preferences › Control/OSC/web)",
    qr_missing = "ReaCue_qrcode.lua not found",
    phone = "phone: %s ✓", phone_badpin = "phone: wrong PIN code",
    cmd = { toggle = "Play/Pause", play = "Play", pause = "Pause", stop = "Stop", prev = "Previous",
      next = "Next", home = "Start", song = "Song", seek = "Section", reh = "Rehearsal", loop = "Loop",
      loopoff = "Loop off", rate = "Speed", mute = "Mute", solo = "Solo", hearall = "Hear all",
      loopsec = "Section loop", ramp = "Speed ramp", pitch = "Transpose", export = "Audio export",
      tctest = "Timecode test 10 s" },
    studio_line = "Studio (computer, tablet): %s",
    concert_n = "Concert %s / %s",
    none = "No concert in this project", building = "Building the concert… %d s",
    open_one = "Open a concert (new tab):", none_in = "No concert in %s",
    ask_claude = "Ask Claude: “concert: song 1, song 2…”",
    n_songs = "%s  ·  %d songs", to_build = "Setlists to build:", build = "Build  %s",
    check = "Check", recheck = "Check again", fix = "Fix", check_title = "Pre-show check",
    all_ready = "All set", n_problems = "%d problem(s)", n_warnings = "%d thing(s) to watch",
    ck = {
      media = "Audio files", media_ok = "%d files readable", media_bad = "%d unreadable or offline: %s",
      voice = "Spoken cues", voice_ok = "%d cues present", voice_bad = "%d cue(s) missing", voice_none = "no spoken cue track",
      fresh = "Concert up to date", fresh_ok = "built on %s, no song changed since",
      fresh_bad = "changed since the build: %s", fresh_unknown = "concert built with an older version: rebuild it once",
      fresh_missing = "project not found: %s",
      songs = "Prepared songs", songs_ok = "%d songs with structure and tempo",
      songs_bad = "prepare then save: %s",
      bridge = "ReaCue bridge", bridge_ok = "running", bridge_bad = "not answering: restart REAPER",
      web = "Web interface (prompter)", web_ok = "on, port %d", web_bad = "not found: Preferences › Control/OSC/web",
      ip = "Network address", ip_ok = "%s", ip_bad = "none: connect the computer to the band's Wi-Fi",
      audio = "Audio device", audio_ok = "running · %s · %d outputs", audio_bad = "stopped: Preferences › Audio › Device",
      outs = "Click and cue outputs", outs_ok = "%s", outs_bad = "%s", outs_master = "to the main output",
      outs_hw = "%s → outputs %d/%d", outs_missing = "%s → output %d missing (the device has %d)",
      outs_nowhere = "%s is not routed anywhere", outs_muted = "%s is muted", outs_none = "no CLICK track",
      prompter = "Phones' prompter", prompter_ok = "page and concert published", prompter_bad = "out of date: republish",
      regie = "Stage control phones", regie_ok = "seen %d s ago", regie_none = "no Stage control phone yet",
      mix = "Cut stems", mix_some = "%s", mix_none = "none: all stems are played", mix_all = "all stems are cut",
    },
    reh = "Rehearsal", reh_on = "REHEARSAL", reh_loop = "loop: %s", reh_loop_range = "loop: %s → %s",
    reh_noloop = "tap a section to loop it (2nd section = range)",
    loop_off = "Loop off", reh_exit = "Exit", rate = "%d %%",
    auto_off = "auto stop off (rehearsal)",
    instruments = "Instruments (stems)", hear_all = "Hear everything", back_profile = "Profile",
    mix_none = "no instrument track", solo_hint = "long press = solo",
    mix_played = "playing", mix_cut = "muted", mix_solo = "solo",
    live_title = "Played live", live_hint = "Ticked = played for real by the band: its stem is cut",
    live_exc = "Per-song exceptions", live_exc_hint = "click: stem / live / profile",
    live_exc_stem = "stem", live_exc_live = "live", live_exc_def = "·",
    live_saved = "profile saved", live_nosetlist = "Setlist not found: rebuild the concert.",
  },
}
function L.lang() return R.lang() end
function L.tr(key) local l = TXT[R.lang()] or TXT.fr; local v = l[key]; if v == nil then v = TXT.fr[key] end return v end

function L.read(p)
  local f = io.open(p, "rb"); if not f then return nil end
  local s = f:read("*a"); f:close(); return s
end

function L.exists(p) local f = io.open(p, "rb"); if f then f:close() return true end return false end

function L.project_file()
  local _, fn = reaper.EnumProjects(-1, "")
  return fn or ""
end

function L.sidecar_for(fn)
  if not fn or fn == "" then return nil end
  return (fn:gsub("%.[Rr][Pp][Pp]$", "")) .. ".concert.lua"
end

-- données pures : chargées sans aucun accès à l'API
function L.load_file(path)
  local src = path and L.read(path)
  if not src then return nil end
  local chunk = load(src, "concert", "t", {})
  if not chunk then return nil end
  local ok, d = pcall(chunk)
  if ok and type(d) == "table" and type(d.songs) == "table" and #d.songs > 0 then
    d.sidecar = path
    return d
  end
  return nil
end

function L.load_concert() return L.load_file(L.sidecar_for(L.project_file())) end

-- morceau contenant le temps t : le dernier dont le début est passé
function L.song_index(c, t)
  local i = 1
  for k, s in ipairs(c.songs) do if s.start <= t + 0.05 then i = k end end
  return i
end

function L.playing() return (reaper.GetPlayState() & 1) == 1 end

function L.pos()
  if L.playing() then return reaper.GetPlayPosition() end
  return reaper.GetCursorPosition()
end

function L.goto_song(c, i)
  i = math.max(1, math.min(#c.songs, i))
  if L.playing() or (reaper.GetPlayState() & 2) == 2 then reaper.OnStopButton() end
  reaper.SetEditCurPos(c.songs[i].start, true, false)
  return i
end

-- « précédent » : au début du morceau en cours si on est dedans, sinon le morceau d'avant
function L.prev(c)
  local t = L.pos()
  local i = L.song_index(c, t)
  if t > c.songs[i].start + 2.0 then return L.goto_song(c, i) end
  return L.goto_song(c, i - 1)
end

function L.next(c)
  return L.goto_song(c, L.song_index(c, L.pos()) + 1)
end

-- arrêt automatique : la lecture a franchi la fin d'un morceau entre deux tours de boucle
-- renvoie l'index du morceau terminé (ou nil)
function L.crossed_stop(c, last, now)
  if not last or not now or now < last or now - last > 1.5 then return nil end
  for k, s in ipairs(c.songs) do
    if last < s.stop and now >= s.stop then return k end
  end
  return nil
end

function L.after_stop(c, k)
  reaper.OnStopButton()
  local nx = c.songs[k + 1]
  reaper.SetEditCurPos(nx and nx.start or c.songs[k].stop, true, false)
end

function L.home() return os.getenv("USERPROFILE") and R.is_windows() and os.getenv("USERPROFILE") or os.getenv("HOME") or os.getenv("USERPROFILE") or "" end

local function settings_text()
  return L.read(reaper.GetResourcePath() .. SEP .. "ReaCueMCP" .. SEP .. "reacue_settings.json")
end

-- dossier des concerts : ExtState ReaCue/concert_dir, puis réglages concert_dir / projects_dir,
-- sinon <Documents>/REAPER Media/Concerts (même règle que reacue_mcp/concert.py)
function L.concert_dir()
  local d = reaper.GetExtState("ReaCue", "concert_dir")
  if d ~= "" then return d end
  local st = settings_text()
  local c = R.jfield(st, "concert_dir")
  if type(c) == "string" and c ~= "" then return (c:gsub("^~", L.home())) end
  local p = R.jfield(st, "projects_dir")
  if type(p) == "string" and p ~= "" then return (p:gsub("^~", L.home())) .. SEP .. "Concerts" end
  return L.home() .. SEP .. "Documents" .. SEP .. "REAPER Media" .. SEP .. "Concerts"
end

-- dossier des projets des morceaux : réglage projects_dir, sinon <Documents>/REAPER Media (comme concert.py)
function L.projects_dir()
  local p = R.jfield(settings_text(), "projects_dir")
  if type(p) == "string" and p ~= "" then return (p:gsub("^~", L.home())) end
  return L.home() .. SEP .. "Documents" .. SEP .. "REAPER Media"
end

function L.list_concerts()
  local dir, out, i = L.concert_dir(), {}, 0
  while true do
    local f = reaper.EnumerateFiles(dir, i)
    if not f then break end
    if f:match("%.concert%.lua$") then
      local d = L.load_file(dir .. SEP .. f)
      if d and d.rpp and L.exists(d.rpp) then out[#out + 1] = d end
    end
    i = i + 1
  end
  table.sort(out, function(a, b) return (a.name or "") < (b.name or "") end)
  return out
end

-- setlists pas encore construites (fichier <nom>.setlist.json sans <nom>.RPP à côté)
function L.list_setlists()
  local dir, out, i = L.concert_dir(), {}, 0
  while true do
    local f = reaper.EnumerateFiles(dir, i)
    if not f then break end
    local stem = f:match("^(.*)%.setlist%.json$")
    if stem and not L.exists(dir .. SEP .. stem .. ".RPP") and not L.exists(dir .. SEP .. stem .. ".rpp") then
      out[#out + 1] = { name = stem, setlist = dir .. SEP .. f, rpp = dir .. SEP .. stem .. ".RPP" }
    end
    i = i + 1
  end
  table.sort(out, function(a, b) return a.name < b.name end)
  return out
end

function L.open_concert(d)
  reaper.Main_OnCommand(40859, 0)            -- nouvel onglet de projet : le projet en cours reste ouvert
  reaper.Main_openProject(d.rpp)
end

-- prompteur : remet en ligne celui du concert (les téléphones suivent tout le concert)
function L.publish_prompter(c)
  if not c.prompter then return false end
  local src = L.read(c.prompter)
  if not src then return false end
  local www = reaper.GetResourcePath() .. SEP .. "reaper_www_root"
  reaper.RecursiveCreateDirectory(www, 0)
  local dst = www .. SEP .. "reacue_song.json"
  if L.read(dst) == src then return true end
  local tmp = dst .. ".tmp"
  local f = io.open(tmp, "wb"); if not f then return false end
  f:write(src); f:close()
  os.remove(dst)
  return os.rename(tmp, dst) and true or false
end

-- ReaCue Studio : page et ressources copiées à côté du prompteur (même liste que reacue_mcp/web/,
-- vérifiée par les tests : tests/test_studio.py)
L.STUDIO_FILES = {
  "studio.html",
  "reacue_studio/base.css", "reacue_studio/core.js", "reacue_studio/travail.css", "reacue_studio/travail.js",
  "reacue_studio/presentation.js", "reacue_studio/prompter-pro.css", "reacue_studio/studio-pro.css",
  "reacue_studio/concert.css", "reacue_studio/concert.js",
  "reacue_studio/biblio.css", "reacue_studio/biblio.js", "reacue_studio/groupe.js",
  "reacue_studio/fonts/OFL-Barlow-Condensed.txt", "reacue_studio/fonts/OFL-IBM-Plex-Mono.txt",
  "reacue_studio/fonts/OFL-IBM-Plex-Sans.txt",
  "reacue_studio/fonts/barlow-condensed-latin-600-normal.woff2", "reacue_studio/fonts/barlow-condensed-latin-700-normal.woff2",
  "reacue_studio/fonts/ibm-plex-mono-latin-400-normal.woff2", "reacue_studio/fonts/ibm-plex-mono-latin-500-normal.woff2",
  "reacue_studio/fonts/ibm-plex-mono-latin-600-normal.woff2", "reacue_studio/fonts/ibm-plex-sans-latin-400-normal.woff2",
  "reacue_studio/fonts/ibm-plex-sans-latin-500-normal.woff2", "reacue_studio/fonts/ibm-plex-sans-latin-600-normal.woff2",
  "reacue_studio/fonts/ibm-plex-sans-latin-700-normal.woff2",
}

-- copie src (contenu) vers dst si différent (écriture atomique) ; true si à jour
local function copy_if_changed(src, dst)
  if L.read(dst) == src then return true end
  local tmp = dst .. ".tmp"
  local f = io.open(tmp, "wb"); if not f then return false end
  f:write(src); f:close()
  os.remove(dst)
  return os.rename(tmp, dst) and true or false
end

-- page du prompteur : copie la version de ReaCue (reacue_mcp/web/prompteur.html) dans reaper_www_root si elle a changé,
-- ainsi que ReaCue Studio (studio.html, reacue_studio/)
function L.publish_page()
  local web = L.install_dir() .. SEP .. "reacue_mcp" .. SEP .. "web"
  local src = L.read(web .. SEP .. "prompteur.html")
  if not src or #src < 1000 then return false end
  local www = reaper.GetResourcePath() .. SEP .. "reaper_www_root"
  reaper.RecursiveCreateDirectory(www, 0)
  local ok = copy_if_changed(src, www .. SEP .. "prompteur.html")
  for _, rel in ipairs(L.STUDIO_FILES) do
    local native = (rel:gsub("/", SEP))
    local s = L.read(web .. SEP .. native)
    if s then
      local dst = www .. SEP .. native
      local dir = dst:match("^(.*)[/\\][^/\\]+$")
      if dir then reaper.RecursiveCreateDirectory(dir, 0) end
      copy_if_changed(s, dst)
    end
  end
  return ok
end

function L.fmt_time(s)
  s = math.max(0, math.floor(s + 0.5))
  return string.format("%d:%02d", s // 60, s % 60)
end

-- QR code du prompteur -------------------------------------------------------------------
local function good_ip(ip)
  return ip and not ip:match("^127%.") and not ip:match("^169%.254%.") and not ip:match("^0%.")
end

-- adresses IPv4 trouvées dans la sortie de ipconfig (Windows : lignes « IPv4 », toutes langues)
function L.parse_windows_ipconfig(out)
  local res, seen = {}, {}
  for line in (out or ""):gmatch("[^\r\n]+") do
    if line:find("IPv4") then
      local ip = line:match(":%s*(%d+%.%d+%.%d+%.%d+)")
      if good_ip(ip) and not seen[ip] then seen[ip] = true; res[#res + 1] = ip end
    end
  end
  return res
end

-- adresses de `hostname -I` (Linux)
function L.parse_hostname_i(out)
  local res = {}
  for ip in (out or ""):gmatch("(%d+%.%d+%.%d+%.%d+)") do if good_ip(ip) then res[#res + 1] = ip end end
  return res
end

-- adresse(s) IPv4 de l'ordinateur sur le réseau local (Wi-Fi / Ethernet), calculées à chaque appel
--   macOS : ipconfig getifaddr en0..en3 ; Windows : ipconfig (sans fenêtre console, via ExecProcess) ;
--   Linux : hostname -I
function L.local_ips()
  local out, seen = {}, {}
  if not reaper.ExecProcess then return out end
  local os_name = reaper.GetOS and reaper.GetOS() or ""
  if R.is_windows() then
    local r = reaper.ExecProcess("ipconfig", 3000)
    return L.parse_windows_ipconfig(r)
  end
  if os_name:match("^Other") or os_name:match("^Linux") then
    local r = reaper.ExecProcess("hostname -I", 1500)
    return L.parse_hostname_i(r and r:gsub("^%-?%d+\n", ""))
  end
  for _, ifc in ipairs({ "en0", "en1", "en2", "en3" }) do
    local r = reaper.ExecProcess("/usr/sbin/ipconfig getifaddr " .. ifc, 1500)
    local ip = r and r:match("\n%s*(%d+%.%d+%.%d+%.%d+)")
    if good_ip(ip) and not seen[ip] then
      seen[ip] = true
      out[#out + 1] = ip
    end
  end
  return out
end

-- port de l'interface web REAPER (reaper.ini : csurf_N=HTTP <flags> <port> ...)
-- renvoie port, trouvée (bool)
function L.parse_web_port(ini)
  if not ini then return 8080, false end
  local cnt = tonumber(ini:match("\ncsurf_cnt=(%d+)")) or tonumber(ini:match("^csurf_cnt=(%d+)"))
  for idx, rest in ini:gmatch("csurf_(%d+)=HTTP%s+([^\r\n]*)") do
    if not cnt or tonumber(idx) < cnt then
      local _, port = rest:match("^(%-?%d+)%s+(%d+)")
      port = tonumber(port)
      if port and port > 0 and port < 65536 then return port, true end
    end
  end
  return 8080, false
end

function L.web_port()
  local ini = reaper.get_ini_file and L.read(reaper.get_ini_file()) or nil
  return L.parse_web_port(ini and ("\n" .. ini))
end

function L.studio_url(ip, port)
  return string.format("http://%s:%d/studio.html", ip, port)
end

function L.prompter_url(ip, port)
  return string.format("http://%s:%d/prompteur.html", ip, port)
end

-- matrice QR (tableau [x][y], >0 = noir) ; niveau de correction M ; nil + message en cas d'échec
local qr_lib
function L.qr_matrix(text, script_dir)
  if not qr_lib then
    local ok, lib = pcall(dofile, (script_dir or LIB_DIR) .. "ReaCue_qrcode.lua")
    if not ok or type(lib) ~= "table" then return nil, L.tr("qr_missing") end
    qr_lib = lib
  end
  local ok, m = qr_lib.qrcode(text, 2)
  if not ok then return nil, tostring(m) end
  return m
end

function L.install_dir() return R.install_dir(LIB_DIR:gsub("[/\\]$", "")) end

-- lance la CLI ReaCue en arrière-plan (ex. « concert --setlist <fichier> », « export --job <fichier> ») ;
-- renvoie true ou false, message
function L.run_cli(cmd, arg_path, flag)
  local windows = R.is_windows()
  local dir = L.install_dir()
  local py = R.python(dir, windows)
  if not L.exists(py) then return false, string.format(L.tr("not_found"), py) end
  local full = cmd .. (arg_path and (" " .. (flag or "--setlist") .. " " .. (windows and R.winq(arg_path) or R.shq(arg_path))) or "")
  local log = reaper.GetResourcePath() .. SEP .. "ReaCueMCP" .. SEP .. "cli.log"
  local line = R.command(full, dir, py, windows, log)
  if windows then
    if reaper.ExecProcess(line, -1) == nil then return false, line end
  else
    os.execute(line)
  end
  return true
end

-- ---------------------------------------------------------------------------------------
-- Pilotage : transport, sections, tonalités, télécommande « Régie » (téléphones)
-- ---------------------------------------------------------------------------------------

function L.play_state()                -- "play" | "pause" | "stop"
  local s = reaper.GetPlayState()
  if (s & 2) == 2 then return "pause" end
  if (s & 1) == 1 then return "play" end
  return "stop"
end

function L.toggle_play()
  local s = L.play_state()
  if s == "stop" then reaper.OnPlayButton() else reaper.OnPauseButton() end
end

function L.stop() reaper.OnStopButton() end

function L.song_home(c) return L.goto_song(c, L.song_index(c, L.pos())) end

-- saut dans le concert ; pendant la lecture, la lecture continue au nouvel endroit
function L.seek(c, t)
  if not t then return false end
  local last = c.songs[#c.songs]
  if t < 0 or t > (last.next or last.stop) + 1 then return false end
  local st = L.play_state()
  reaper.SetEditCurPos(t, true, st == "play")
  return true
end

-- sections (régions du projet) du morceau i : {name, start, stop, color={r,g,b}}
function L.song_sections(c, i)
  local s = c.songs[i]
  if not s then return {} end
  local out, k = {}, 0
  local prefix = (s.title or "") .. " · "
  while true do
    local ok, isrgn, pos, rend, name, _, color = reaper.EnumProjectMarkers3(0, k)
    if not ok or ok == 0 then break end
    if isrgn and pos >= s.start - 0.01 and pos < s.stop - 0.01 then
      local nm = name or ""
      if nm:sub(1, #prefix) == prefix then nm = nm:sub(#prefix + 1) end
      local rgb = nil
      if color and color ~= 0 then
        local r, g, b = reaper.ColorFromNative(color & 0xFFFFFF)
        rgb = { r, g, b }
      end
      out[#out + 1] = { name = nm, start = pos, stop = rend, color = rgb }
    end
    k = k + 1
  end
  table.sort(out, function(a, b) return a.start < b.start end)
  return out
end

function L.section_at(secs, t)
  local cur = nil
  for k, x in ipairs(secs) do if x.start <= t + 0.02 then cur = k end end
  if cur and t >= secs[cur].stop + 0.02 then return nil end
  return cur
end

-- mesure du morceau (1 = première mesure ; <= 0 = décompte)
function L.bar_of(s, t)
  if not reaper.TimeMap2_timeToBeats then return nil end
  local _, m = reaper.TimeMap2_timeToBeats(0, t)
  local _, m1 = reaper.TimeMap2_timeToBeats(0, s.bar1 or s.start)
  if not m or not m1 then return nil end
  return m - m1 + 1
end

-- tonalités lues dans le prompteur du concert (dans l'ordre des morceaux) : {"Gbm", false, "Em", ...}
function L.song_keys(c)
  local src = c.prompter and L.read(c.prompter)
  local out = {}
  if not src then return out end
  local p = 1
  while true do
    local a, b = src:find('"key"%s*:%s*', p)
    if not a then break end
    local v = src:sub(b + 1, b + 1)
    if v == "{" then
      local obj = src:match("^%b{}", b + 1) or ""
      out[#out + 1] = obj:match('"chord"%s*:%s*"([^"]*)"') or false
    else
      out[#out + 1] = false
    end
    p = b + 1
  end
  return out
end

-- ---------------------------------------------------------------------------------------
-- Contrôle avant concert (« Vérifier ») : liste de {id, status = ok|warn|bad|info, label, detail, fix}
-- ---------------------------------------------------------------------------------------
-- pistes générées (jamais coupées par la répétition ; le timecode continue de piloter la lumière)
local GEN_TRACKS = { CLICK = true, VOIX = true, VOICE = true, CUES = true, ["TIMECODE LTC"] = true, ["TIMECODE MTC"] = true }
local VOICE_TRACKS = { VOIX = true, VOICE = true }

-- Adler-32 (même valeur que zlib.adler32 côté Python) : empreinte du projet d'un morceau
function L.adler32(s)
  local a, b = 1, 0
  local n = #s
  for i = 1, n, 4096 do
    local t = { s:byte(i, math.min(n, i + 4095)) }
    for k = 1, #t do a = (a + t[k]) % 65521; b = (b + a) % 65521 end
  end
  return (b << 16) | a
end

local function track_name(tr)
  local _, name = reaper.GetTrackName(tr)
  return name or ""
end

local function short_name(p) return (tostring(p):match("([^/\\]+)$") or tostring(p)) end

local function join_names(list, max)
  max = max or 3
  local out = {}
  for k = 1, math.min(#list, max) do out[k] = list[k] end
  local s = table.concat(out, ", ")
  if #list > max then s = s .. " (+" .. (#list - max) .. ")" end
  return s
end

-- fichiers audio des items : lisibles et en ligne ? (voix d'annonces comptées à part)
function L.scan_media()
  local r = { n = 0, bad = {}, voice_n = 0, voice_bad = 0, has_voice = false }
  local seen = {}
  if not reaper.CountMediaItems then return r end
  for i = 0, reaper.CountMediaItems(0) - 1 do
    local it = reaper.GetMediaItem(0, i)
    local tk = it and reaper.GetActiveTake(it)
    if tk and not (reaper.TakeIsMIDI and reaper.TakeIsMIDI(tk)) then
      local src = reaper.GetMediaItemTake_Source(tk)
      local parent = src and reaper.GetMediaSourceParent and reaper.GetMediaSourceParent(src)
      while parent do src = parent; parent = reaper.GetMediaSourceParent(src) end
      local fn = src and reaper.GetMediaSourceFileName(src, "") or ""
      if fn ~= "" then
        local tname = track_name(reaper.GetMediaItem_Track(it))
        local ok = L.exists(fn)
        if ok and reaper.GetMediaSourceSampleRate and reaper.GetMediaSourceSampleRate(src) == 0 then ok = false end
        if VOICE_TRACKS[tname] then
          r.has_voice = true
          r.voice_n = r.voice_n + 1
          if not ok then r.voice_bad = r.voice_bad + 1 end
        elseif not seen[fn] then
          seen[fn] = true
          r.n = r.n + 1
          if not ok then r.bad[#r.bad + 1] = short_name(fn) end
        end
      end
    end
  end
  return r
end

-- sorties du click et des annonces : envois matériels existants, pas de piste muette ou isolée
function L.scan_outputs()
  local nout = reaper.GetNumAudioOutputs and reaper.GetNumAudioOutputs() or 0
  local ok_l, bad_l, found = {}, {}, false
  local ck = L.tr("ck")
  for i = 0, (reaper.CountTracks and reaper.CountTracks(0) or 0) - 1 do
    local tr = reaper.GetTrack(0, i)
    local name = track_name(tr)
    if name == "CLICK" or VOICE_TRACKS[name] then
      if name == "CLICK" then found = true end
      if reaper.GetMediaTrackInfo_Value(tr, "B_MUTE") > 0 then bad_l[#bad_l + 1] = string.format(ck.outs_muted, name) end
      local main = reaper.GetMediaTrackInfo_Value(tr, "B_MAINSEND") > 0
      local nsend = reaper.GetTrackNumSends and reaper.GetTrackNumSends(tr, 1) or 0
      if main then ok_l[#ok_l + 1] = name .. " " .. ck.outs_master end
      for k = 0, nsend - 1 do
        local dst = math.floor(reaper.GetTrackSendInfo_Value(tr, 1, k, "I_DSTCHAN"))
        local ch = dst & 1023
        local mono = (dst & 1024) ~= 0
        local need = ch + (mono and 1 or 2)
        if nout > 0 and need > nout then
          bad_l[#bad_l + 1] = string.format(ck.outs_missing, name, need, nout)
        else
          ok_l[#ok_l + 1] = string.format(ck.outs_hw, name, ch + 1, ch + (mono and 1 or 2))
        end
      end
      if not main and nsend == 0 then bad_l[#bad_l + 1] = string.format(ck.outs_nowhere, name) end
    end
  end
  return found, ok_l, bad_l
end

local function fmt_date(t)
  if not t then return "?" end
  return os.date(L.lang() == "en" and "%Y-%m-%d %H:%M" or "%d/%m/%Y %H:%M", t)
end

-- état « vu » des téléphones Régie : renseigné par la fenêtre (L.regie_seen = time_precise de la dernière vue)
L.regie_seen = nil

-- liste complète ; opts.c = concert (ou nil), opts.ips (sinon calculées), opts.now
function L.run_checks(c, opts)
  opts = opts or {}
  local ck = L.tr("ck")
  local out = {}
  local function add(id, status, label, detail, fix) out[#out + 1] = { id = id, status = status, label = label, detail = detail or "", fix = fix } end
  if c then
    -- médias
    local m = L.scan_media()
    if #m.bad == 0 then add("media", "ok", ck.media, string.format(ck.media_ok, m.n))
    else add("media", "bad", ck.media, string.format(ck.media_bad, #m.bad, join_names(m.bad)), "media") end
    if not m.has_voice then add("voice", "info", ck.voice, ck.voice_none)
    elseif m.voice_bad == 0 then add("voice", "ok", ck.voice, string.format(ck.voice_ok, m.voice_n))
    else add("voice", "bad", ck.voice, string.format(ck.voice_bad, m.voice_bad), "rebuild") end
    -- morceaux préparés (structure + tempo)
    local unprep = {}
    for _, s in ipairs(c.songs) do
      if (tonumber(s.sections) or 0) < 1 or (tonumber(s.bars) or 0) < 1 then unprep[#unprep + 1] = s.title end
    end
    if #unprep == 0 then add("songs", "ok", ck.songs, string.format(ck.songs_ok, #c.songs))
    else add("songs", "bad", ck.songs, string.format(ck.songs_bad, join_names(unprep))) end
    -- concert à jour : empreinte du projet de chaque morceau
    local changed, missing, unknown = {}, {}, false
    for _, s in ipairs(c.songs) do
      local src = s.project and L.read(s.project)
      if not src then missing[#missing + 1] = s.title
      elseif not s.project_sum then unknown = true
      elseif #src ~= s.project_size or L.adler32(src) ~= s.project_sum then changed[#changed + 1] = s.title end
    end
    if #missing > 0 then add("fresh", "bad", ck.fresh, string.format(ck.fresh_missing, join_names(missing)))
    elseif #changed > 0 then add("fresh", "warn", ck.fresh, string.format(ck.fresh_bad, join_names(changed)), "rebuild")
    elseif unknown then add("fresh", "warn", ck.fresh, ck.fresh_unknown, "rebuild")
    else add("fresh", "ok", ck.fresh, string.format(ck.fresh_ok, fmt_date(c.built))) end
  end
  -- pont, interface web, adresse IP
  if L.R.bridge_alive and L.R.bridge_alive() then add("bridge", "ok", ck.bridge, ck.bridge_ok)
  else add("bridge", "bad", ck.bridge, ck.bridge_bad, "bridge") end
  local port, found = L.web_port()
  if found then add("web", "ok", ck.web, string.format(ck.web_ok, port)) else add("web", "bad", ck.web, ck.web_bad, "web") end
  local ips = opts.ips or L.local_ips()
  if #ips > 0 then add("ip", "ok", ck.ip, string.format(ck.ip_ok, L.prompter_url(ips[1], port)))
  else add("ip", "bad", ck.ip, ck.ip_bad) end
  -- carte son et sorties
  local running = reaper.Audio_IsRunning and reaper.Audio_IsRunning() or 0
  local nout = reaper.GetNumAudioOutputs and reaper.GetNumAudioOutputs() or 0
  if running ~= 0 and running ~= false then
    local dev = ""
    if reaper.GetAudioDeviceInfo then local _, d = reaper.GetAudioDeviceInfo("IDENT_OUT", ""); dev = d or "" end
    add("audio", "ok", ck.audio, string.format(ck.audio_ok, dev ~= "" and dev or "?", nout))
  else
    add("audio", "bad", ck.audio, ck.audio_bad)
  end
  if c then
    local found_click, okl, badl = L.scan_outputs()
    if not found_click then add("outs", "warn", ck.outs, ck.outs_none)
    elseif #badl > 0 then add("outs", "bad", ck.outs, string.format(ck.outs_bad, table.concat(badl, " · ")))
    else add("outs", "ok", ck.outs, string.format(ck.outs_ok, table.concat(okl, " · "))) end
    -- prompteur publié et à jour
    local www = reaper.GetResourcePath() .. SEP .. "reaper_www_root" .. SEP
    local page = L.read(L.install_dir() .. SEP .. "reacue_mcp" .. SEP .. "web" .. SEP .. "prompteur.html")
    local pub_ok = (not page or L.read(www .. "prompteur.html") == page)
      and (not c.prompter or not L.read(c.prompter) or L.read(www .. "reacue_song.json") == L.read(c.prompter))
    if pub_ok then add("prompter", "ok", ck.prompter, ck.prompter_ok)
    else add("prompter", "warn", ck.prompter, ck.prompter_bad, "publish") end
  end
  -- stems coupés (information)
  if c then
    local cut, n = {}, 0
    for _, g in ipairs(L.instr_tracks()) do
      n = n + 1
      local m = 0
      for _, tr in ipairs(g.tracks) do m = math.max(m, L.track_mute_wanted(tr)) end
      if m > 0 then cut[#cut + 1] = g.label end
    end
    if n > 0 then
      local d = (#cut == 0) and ck.mix_none or ((#cut == n) and ck.mix_all or string.format(ck.mix_some, table.concat(cut, ", ")))
      add("mix", "info", ck.mix, d)
    end
  end
  -- téléphones Régie (information)
  local now = opts.now or reaper.time_precise()
  if L.regie_seen and now - L.regie_seen < 600 then
    add("regie", "info", ck.regie, string.format(ck.regie_ok, math.floor(now - L.regie_seen)))
  else
    add("regie", "info", ck.regie, ck.regie_none)
  end
  return out
end

-- résumé : nombre de problèmes (bad) et de points à surveiller (warn)
function L.check_summary(list)
  local bad, warn = 0, 0
  for _, x in ipairs(list) do
    if x.status == "bad" then bad = bad + 1 elseif x.status == "warn" then warn = warn + 1 end
  end
  return bad, warn
end

-- corrections simples (la reconstruction est lancée par la fenêtre)
function L.apply_fix(c, fix)
  if fix == "media" then reaper.Main_OnCommand(40101, 0); return true      -- Item: Set all media online
  elseif fix == "publish" then
    local a = c and L.publish_prompter(c)
    local b = L.publish_page()
    return (a ~= false) and b
  end
  return false
end

-- ---------------------------------------------------------------------------------------
-- Mode répétition : arrêt auto coupé, boucle sur une section ou une plage avec 1 mesure de décompte
-- (click et annonces seuls, les autres pistes coupées) avant chaque reprise, ralenti 100/90/80/70 %.
-- ---------------------------------------------------------------------------------------
local PRESERVE_PITCH = 40671     -- Options: Toggle preserve pitch in audio items when changing master playrate
L.reh = { on = false, loop = nil, anchor = nil, rate = 1.0, saved = nil, prebar = false, muted = nil }

function L.bar_len_before(t, bpm)
  if reaper.TimeMap2_timeToBeats and reaper.TimeMap2_beatsToTime then
    local _, m = reaper.TimeMap2_timeToBeats(0, t + 0.001)
    if m and m >= 1 then
      local t0 = reaper.TimeMap2_beatsToTime(0, 0, m - 1)
      if t0 and t0 < t - 0.01 then return t - t0 end
    end
  end
  return 240 / (bpm and bpm > 0 and bpm or 120)
end

local function music_tracks()
  local out = {}
  for i = 0, (reaper.CountTracks and reaper.CountTracks(0) or 0) - 1 do
    local tr = reaper.GetTrack(0, i)
    if not GEN_TRACKS[track_name(tr)] then out[#out + 1] = tr end
  end
  return out
end

local function mute_music(on)   -- (défini plus bas : L.set_track_mute tient compte de cet état)
  local R_ = L.reh
  if on then
    if R_.muted then return end
    R_.muted = {}
    for _, tr in ipairs(music_tracks()) do
      R_.muted[#R_.muted + 1] = { tr, reaper.GetMediaTrackInfo_Value(tr, "B_MUTE") }
      reaper.SetMediaTrackInfo_Value(tr, "B_MUTE", 1)
    end
  elseif R_.muted then
    for _, x in ipairs(R_.muted) do reaper.SetMediaTrackInfo_Value(x[1], "B_MUTE", x[2]) end
    R_.muted = nil
  end
end

function L.publish_reh()
  local R_ = L.reh
  local lp = R_.loop
  reaper.SetExtState("ReaCue", "rehearsal", string.format("%d|%.2f|%s|%s|%s", R_.on and 1 or 0, R_.rate,
    lp and string.format("%.3f", lp.start) or "", lp and string.format("%.3f", lp.stop) or "",
    lp and (lp.names or "") or ""), false)
end

function L.set_rate(r)
  r = tonumber(r)
  if not r or r < 0.5 or r > 1.0 then return false end
  if r < 0.999 and reaper.GetToggleCommandState and reaper.GetToggleCommandState(PRESERVE_PITCH) == 0 then
    reaper.Main_OnCommand(PRESERVE_PITCH, 0)
    L.reh.pitch_switched = true
  end
  if reaper.CSurf_OnPlayRateChange then reaper.CSurf_OnPlayRateChange(r) end
  L.reh.rate = r
  L.publish_reh()
  return true
end

function L.loop_off()
  local R_ = L.reh
  mute_music(false)
  if R_.ramp then R_.ramp = nil; if R_.on then L.set_rate(1.0) end end
  R_.loop, R_.anchor, R_.prebar = nil, nil, false
  if reaper.GetSet_LoopTimeRange then reaper.GetSet_LoopTimeRange(true, true, 0, 0, false) end
  L.publish_reh()
end

function L.set_rehearsal(on)
  local R_ = L.reh
  if on and not R_.on then
    local s0, s1 = 0, 0
    if reaper.GetSet_LoopTimeRange then s0, s1 = reaper.GetSet_LoopTimeRange(false, true, 0, 0, false) end
    R_.saved = { rep = reaper.GetSetRepeat and reaper.GetSetRepeat(-1) or 0, sel = { s0 or 0, s1 or 0 },
                 rate = reaper.Master_GetPlayRate and reaper.Master_GetPlayRate(0) or 1 }
    R_.on = true
    R_.pitch_switched = false
    if reaper.GetSetRepeat then reaper.GetSetRepeat(0) end          -- la boucle est pilotée par la fenêtre
  elseif not on and R_.on then
    L.loop_off()
    if reaper.CSurf_OnPlayRateChange then reaper.CSurf_OnPlayRateChange(1.0) end
    if R_.pitch_switched and reaper.GetToggleCommandState and reaper.GetToggleCommandState(PRESERVE_PITCH) == 1 then
      reaper.Main_OnCommand(PRESERVE_PITCH, 0)
    end
    local sv = R_.saved or {}
    if reaper.GetSetRepeat and sv.rep then reaper.GetSetRepeat(sv.rep) end
    if reaper.GetSet_LoopTimeRange and sv.sel then reaper.GetSet_LoopTimeRange(true, true, sv.sel[1], sv.sel[2], false) end
    R_.on, R_.rate, R_.saved, R_.pitch_switched = false, 1.0, nil, false
  end
  L.publish_reh()
  return true
end

-- (re)lance la boucle : 1 mesure avant son début, pistes musicales coupées pendant cette mesure
function L.loop_restart()
  local lp = L.reh.loop
  if not lp then return end
  local rp = L.reh.ramp                 -- rampe de vitesse (Studio) : un palier de plus à chaque passage
  if rp then
    rp.pass = rp.pass + 1
    L.set_rate(L.ramp_rate(rp, rp.pass))
  end
  mute_music(true)
  L.reh.prebar = true
  reaper.SetEditCurPos(lp.start - lp.pre, true, true)
  if not L.playing() then reaper.OnPlayButton() end
end

function L.loop_set(c, a, b)
  local R_ = L.reh
  if not R_.on then L.set_rehearsal(true) end
  local i = L.song_index(c, a.start + 0.01)
  local lp = { start = a.start, stop = b.stop, song = i, names = (a == b) and a.name or (a.name .. " → " .. b.name),
               a = a.name, b = b.name }
  lp.pre = L.bar_len_before(a.start, c.songs[i] and c.songs[i].bpm)
  mute_music(false)
  if R_.ramp then R_.ramp.pass = 0 end   -- nouvelle boucle : la rampe repart du début
  R_.loop = lp
  if reaper.GetSet_LoopTimeRange then reaper.GetSet_LoopTimeRange(true, true, lp.start, lp.stop, false) end
  L.publish_reh()
  L.loop_restart()
  return lp
end

-- appui sur la section commençant au temps t : 1er appui = boucle sur cette section,
-- 2e appui sur une autre section du même morceau = boucle de l'une à l'autre (plage)
function L.loop_tap(c, t)
  t = tonumber(t)
  if not t then return false end
  local i = L.song_index(c, t + 0.01)
  local secs = L.song_sections(c, i)
  local k = nil
  for n, x in ipairs(secs) do if math.abs(x.start - t) < 0.05 then k = n end end
  if not k then k = L.section_at(secs, t) end
  if not k then return false end
  local R_ = L.reh
  local an = R_.anchor
  if an and an.song == i and an.k ~= k and R_.loop then
    local lo, hi = math.min(an.k, k), math.max(an.k, k)
    L.loop_set(c, secs[lo], secs[hi])
    R_.anchor = nil
  else
    L.loop_set(c, secs[k], secs[k])
    R_.anchor = { song = i, k = k }
  end
  return true
end

-- à appeler à chaque tour de boucle de la fenêtre (position de lecture précédente / actuelle)
function L.loop_tick(last, now)
  local R_ = L.reh
  local lp = R_.loop
  if not lp then return nil end
  if not L.playing() then
    if R_.prebar then mute_music(false); R_.prebar = false end      -- arrêt pendant la mesure de décompte
    return nil
  end
  if R_.prebar and (now >= lp.start - 0.03 or now < lp.start - lp.pre - 0.5) then
    mute_music(false); R_.prebar = false                             -- début de la boucle (ou saut ailleurs)
    return "start"
  end
  if last and now >= last and now - last < 1.5 and last < lp.stop and now >= lp.stop then
    L.loop_restart()
    return "restart"
  end
  return nil
end

-- télécommande ---------------------------------------------------------------------------
-- Le téléphone écrit, via l'interface web de REAPER :
--   /_/SET/EXTSTATE/ReaCue/remote/<cmd>|<arg>|<pin>|<nonce>      (valeur urlencodée)
-- La fenêtre Concert lit, efface, vérifie le PIN et le nonce, exécute, puis répond :
--   ExtState ReaCue/remote_ack = <nonce>|ok   (ou |badpin, |bad)
-- et signale qu'elle tourne : ExtState ReaCue/remote_alive = compteur qui avance.
local REMOTE = "ReaCue"

function L.remote_pin()
  local p = reaper.GetExtState(REMOTE, "remote_pin")
  if not p:match("^%d%d%d%d$") then
    math.randomseed(math.floor((reaper.time_precise() * 1000) % 2147483647) + os.time())
    p = string.format("%04d", math.random(0, 9999))
    reaper.SetExtState(REMOTE, "remote_pin", p, true)
  end
  return p
end

function L.set_remote_pin(p)
  if type(p) ~= "string" or not p:match("^%d%d%d%d$") then return false end
  reaper.SetExtState(REMOTE, "remote_pin", p, true)
  return true
end

function L.remote_alive(now)
  reaper.SetExtState(REMOTE, "remote_alive", tostring(math.floor((now or reaper.time_precise()) * 2)), false)
end

function L.remote_off()
  reaper.SetExtState(REMOTE, "remote_alive", "", false)
end

-- commandes ajoutées par la fenêtre ReaCue (besoin de ses onglets) : L.remote_ext[cmd] = function(c, arg) -> bool
-- (tctest : test d'envoi du timecode de l'onglet Lumière)
L.remote_ext = L.remote_ext or {}

function L.remote_exec(c, cmd, arg)
  local ext = L.remote_ext[cmd]
  if ext then return ext(c, arg) and true or false end
  if cmd == "toggle" then L.toggle_play()
  elseif cmd == "play" then if L.play_state() ~= "play" then L.toggle_play() end
  elseif cmd == "pause" then if L.play_state() == "play" then reaper.OnPauseButton() end
  elseif cmd == "stop" then L.stop()
  elseif cmd == "prev" then L.prev(c)
  elseif cmd == "next" then L.next(c)
  elseif cmd == "home" then L.song_home(c)
  elseif cmd == "song" then
    local k = tonumber(arg)
    if not k or not c.songs[k] then return false end
    L.goto_song(c, k)
  elseif cmd == "seek" then
    if not L.seek(c, tonumber(arg)) then return false end
  elseif cmd == "reh" then
    L.set_rehearsal(arg == "1")
  elseif cmd == "loop" then
    if not L.loop_tap(c, arg) then return false end
  elseif cmd == "loopoff" then
    L.loop_off()
  elseif cmd == "rate" then
    if not L.reh.on then L.set_rehearsal(true) end
    if not L.set_rate(arg) then return false end
  elseif cmd == "mute" then
    if not L.mix_toggle(c, arg) then return false end
  elseif cmd == "solo" then
    if not L.mix_solo(c, arg) then return false end
  elseif cmd == "hearall" then
    L.mix_hear_all(c, arg == "1")
  elseif cmd == "loopsec" then                  -- ReaCue Studio : boucle d'une seule section
    if not L.loop_section(c, arg) then return false end
  elseif cmd == "ramp" then                     -- rampe de vitesse « de:à:passages[:début de section] »
    if not L.set_ramp(c, arg) then return false end
  elseif cmd == "pitch" then                    -- transposition « +1 », « -1 », « 0 »
    if not L.transpose(c, arg) then return false end
  elseif cmd == "export" then                   -- export audio (demande dans ReaCue/export_req)
    if not L.studio_export(c, arg) then return false end
  elseif cmd == "note" then                     -- GROUPE : note de section « morceau:mesure:texte »
    if not L.set_note(c, arg) then return false end
  elseif cmd == "libstage" then                 -- BIBLIO : étape du parcours réglée à la main
    if not L.set_stage(arg) then return false end
  elseif cmd == "readyreset" then               -- GROUPE : remise à zéro des « Prêt »
    L.band_reset()
  elseif cmd == "resume" then                   -- GROUPE : « On reprend à… » (1 mesure avant la section)
    if not L.resume_at(c, arg) then return false end
  else
    return false
  end
  return true
end

-- commandes possibles sans morceau ni concert reconnu (projet quelconque)
local NO_CONCERT_OK = { pitch = true, export = true, tctest = true, open = true, libstage = true, readyreset = true }

-- traite au plus une commande en attente ; renvoie cmd, résultat ("ok", "badpin", "bad", "dup") ou nil
local seen, seen_list = {}, {}
function L.remote_poll(c)
  local v = reaper.GetExtState(REMOTE, "remote")
  if v == nil or v == "" then return nil end
  reaper.SetExtState(REMOTE, "remote", "", false)
  local cmd, arg, pin, nonce = v:match("^([%w_]+)|([^|]*)|(%d*)|([%w%-]+)$")
  if not cmd then return nil, "bad" end
  if seen[nonce] then return cmd, "dup" end
  seen[nonce] = true
  seen_list[#seen_list + 1] = nonce
  if #seen_list > 64 then seen[table.remove(seen_list, 1)] = nil end
  local res
  if pin ~= L.remote_pin() then res = "badpin"
  elseif not c and not NO_CONCERT_OK[cmd] then res = "noconcert"
  else res = L.remote_exec(c, cmd, arg) and "ok" or "bad" end
  reaper.SetExtState(REMOTE, "remote_ack", nonce .. "|" .. res, false)
  return cmd, res
end

-- téléphones Régie : la page écrit ReaCue/remote_seen (valeur qui change) toutes les quelques secondes
local last_seen_v = nil
function L.poll_seen(now)
  local v = reaper.GetExtState(REMOTE, "remote_seen")
  if v ~= "" and v ~= last_seen_v then
    if last_seen_v ~= nil then L.regie_seen = now or reaper.time_precise() end
    last_seen_v = v
  end
end

-- ---------------------------------------------------------------------------------------
-- Instruments (stems) : mute / solo par instrument et profil « joué en live » du concert.
-- Profil enregistré dans <concert>.setlist.json : "live" = rôles joués en vrai (stems coupés),
-- "live_exceptions" = {titre: {rôle: "live"|"stem"}}. Les choix manuels (mute, solo) valent pour le
-- morceau en cours : en entrant dans un autre morceau, le profil (et ses exceptions) s'applique.
-- ---------------------------------------------------------------------------------------
L.ROLES = {          -- même ordre et mêmes noms que reacue_mcp/concert.py (ROLE_TRACKS_I18N)
  { "vocals", "Chant", "Vocals", { 212, 83, 126 } },
  { "drums", "Batterie", "Drums", { 186, 117, 23 } },
  { "bass", "Basse", "Bass", { 24, 95, 165 } },
  { "guitars", "Guitares", "Guitars", { 99, 153, 34 } },
  { "lead_guitar", "Guitare solo", "Lead guitar", { 15, 110, 86 } },
  { "keys", "Claviers", "Keys", { 127, 119, 221 } },
  { "other", "Autres", "Other", { 136, 135, 128 } },
  { "mix", "Mix", "Mix", { 95, 94, 90 } },
}
local ROLE_BY_NAME = {}
local LOWER = { ["À"] = "à", ["Â"] = "â", ["Ä"] = "ä", ["Á"] = "á", ["Ç"] = "ç", ["É"] = "é", ["È"] = "è",
  ["Ê"] = "ê", ["Ë"] = "ë", ["Î"] = "î", ["Ï"] = "ï", ["Í"] = "í", ["Ô"] = "ô", ["Ö"] = "ö", ["Ó"] = "ó",
  ["Ù"] = "ù", ["Û"] = "û", ["Ü"] = "ü", ["Ú"] = "ú", ["Ÿ"] = "ÿ", ["Ñ"] = "ñ", ["Æ"] = "æ", ["Œ"] = "œ" }
function L.lower_utf8(s)
  s = tostring(s or ""):gsub("[A-Z]", function(c) return string.char(c:byte() + 32) end)
  return (s:gsub("[\xC3\xC5][\x80-\xBF]", function(c) return LOWER[c] or c end))
end
for _, r in ipairs(L.ROLES) do ROLE_BY_NAME[L.lower_utf8(r[2])] = r[1]; ROLE_BY_NAME[L.lower_utf8(r[3])] = r[1] end
-- pistes d'un morceau séparé par ReaCue (« Guitare », « Piano »…) : mêmes rôles
for k, v in pairs({ guitare = "guitars", guitar = "guitars", piano = "keys", clavier = "keys", synth = "keys",
                    batt = "drums", ["lead guitars"] = "lead_guitar" }) do
  ROLE_BY_NAME[k] = v
end
function L.role_info(role)
  for _, r in ipairs(L.ROLES) do if r[1] == role then return r end end
  return nil
end
function L.role_label(role)
  local r = L.role_info(role)
  if not r then return role end
  return L.lang() == "en" and r[3] or r[2]
end
-- rôle d'une piste commune du concert (« Basse », « Bass 2 »…) ou nil
function L.role_of_track(name)
  local n = L.lower_utf8((name or ""):gsub("[ \t\r\n\v\f]+%d+$", ""))
  return ROLE_BY_NAME[n]
end
-- noms acceptés pour un rôle (commandes distantes) : rôle, nom FR ou EN
function L.norm_role(x)
  x = L.lower_utf8(x)
  for _, r in ipairs(L.ROLES) do
    if x == r[1] or x == L.lower_utf8(r[2]) or x == L.lower_utf8(r[3]) then return r[1] end
  end
  return nil
end

-- pistes d'instruments présentes, dans l'ordre des rôles : {role, label, color, tracks}
function L.instr_tracks()
  local by = {}
  for i = 0, (reaper.CountTracks and reaper.CountTracks(0) or 0) - 1 do
    local tr = reaper.GetTrack(0, i)
    local role = L.role_of_track(track_name(tr))
    if role then by[role] = by[role] or {}; table.insert(by[role], tr) end
  end
  local out = {}
  for _, r in ipairs(L.ROLES) do
    if by[r[1]] then out[#out + 1] = { role = r[1], label = L.role_label(r[1]), color = r[4], tracks = by[r[1]] } end
  end
  return out
end

L.mix = { live = {}, exc = {}, manual = {}, solo = nil, hear_all = false, song = nil, src = nil, t = -1e9 }

-- relit le profil dans la setlist du concert ; true s'il a changé
function L.load_live(c, force)
  local M = L.mix
  local src = c and c.setlist and L.read(c.setlist) or nil
  if not force and src == M.src then return false end
  M.src = src
  M.live, M.exc = {}, {}
  local d = src and R.json_decode(src)
  if type(d) == "table" then
    for _, r in ipairs(type(d.live) == "table" and d.live or {}) do
      local role = L.norm_role(r)
      if role then M.live[role] = true end
    end
    if type(d.live_exceptions) == "table" then
      for title, v in pairs(d.live_exceptions) do
        if type(v) == "table" then
          M.exc[title] = {}
          for r, m in pairs(v) do
            local role = L.norm_role(r)
            if role and (m == "live" or m == "stem") then M.exc[title][role] = m end
          end
        end
      end
    end
  end
  return true
end

-- mode du profil pour le rôle dans le morceau i : "live" (stem coupé) ou "stem" (stem joué)
function L.profile_mode(c, i, role)
  local s = c and c.songs and c.songs[i]
  local e = s and L.mix.exc[s.title]
  if e and e[role] then return e[role] end
  return L.mix.live[role] and "live" or "stem"
end

-- le stem du rôle doit-il s'entendre ?
function L.mix_audible(c, i, role)
  local M = L.mix
  if M.hear_all then return true end
  if M.solo then return role == M.solo end
  if M.manual[role] ~= nil then return M.manual[role] end
  return L.profile_mode(c, i, role) ~= "live"
end

-- mute voulu d'une piste (tient compte de la mesure de décompte de la répétition)
function L.track_mute_wanted(tr)
  if L.reh.muted then
    for _, x in ipairs(L.reh.muted) do if x[1] == tr then return x[2] end end
  end
  return reaper.GetMediaTrackInfo_Value(tr, "B_MUTE")
end

-- pose le mute voulu ; pendant la mesure de décompte, les pistes restent coupées et l'état voulu est
-- mémorisé pour être rétabli au début de la section
function L.set_track_mute(tr, v)
  if L.reh.muted then
    for _, x in ipairs(L.reh.muted) do
      if x[1] == tr then x[2] = v; return end
    end
  end
  if reaper.GetMediaTrackInfo_Value(tr, "B_MUTE") ~= v then reaper.SetMediaTrackInfo_Value(tr, "B_MUTE", v) end
end

function L.mix_publish(c, i)
  local M = L.mix
  local parts = {}
  for _, g in ipairs(L.instr_tracks()) do
    parts[#parts + 1] = g.role .. "=" .. (L.mix_audible(c, i, g.role) and "1" or "0") ..
      (L.profile_mode(c, i, g.role) == "live" and "L" or "")
  end
  reaper.SetExtState("ReaCue", "mix", table.concat(parts, ",") .. ";" .. (M.solo or "") .. ";" ..
    (M.hear_all and "1" or "0") .. ";" .. tostring(i or 0), false)
end

function L.mix_apply(c, i)
  if not c then return end
  i = i or L.song_index(c, L.pos())
  for _, g in ipairs(L.instr_tracks()) do
    local v = L.mix_audible(c, i, g.role) and 0 or 1
    for _, tr in ipairs(g.tracks) do L.set_track_mute(tr, v) end
  end
  L.mix_publish(c, i)
end

local function cur_song(c) return L.song_index(c, L.pos()) end

function L.mix_toggle(c, role)
  role = L.norm_role(role)
  if not c or not role then return false end
  local i = cur_song(c)
  local now = L.mix_audible(c, i, role)
  local M = L.mix
  if M.hear_all or M.solo then           -- quitter « tout entendre » / solo en gardant ce qu'on entend
    for _, g in ipairs(L.instr_tracks()) do M.manual[g.role] = L.mix_audible(c, i, g.role) end
    M.hear_all, M.solo = false, nil
  end
  M.manual[role] = not now
  L.mix_apply(c, i)
  return true
end

function L.mix_solo(c, role)
  role = L.norm_role(role)
  if not c or not role then return false end
  local M = L.mix
  M.solo = (M.solo == role) and nil or role
  M.hear_all = false
  L.mix_apply(c)
  return true
end

-- « Tout entendre » : tous les stems ; off = retour au profil (choix manuels effacés)
function L.mix_hear_all(c, on)
  local M = L.mix
  M.hear_all = on and true or false
  M.solo = nil
  M.manual = {}
  L.mix_apply(c)
  return true
end

function L.mix_reset(c)
  local M = L.mix
  M.manual, M.solo, M.hear_all = {}, nil, false
  L.mix_apply(c)
end

-- à chaque tour de boucle : entrée dans un autre morceau, profil modifié (Claude, autre fenêtre)
function L.mix_tick(c, now)
  if not c then return false end
  local M = L.mix
  local i = cur_song(c)
  local changed = false
  now = now or reaper.time_precise()
  if now - M.t > 1.5 then
    M.t = now
    if L.load_live(c) then changed = true end
  end
  if i ~= M.song then
    M.song = i
    M.manual, M.solo = {}, nil
    changed = true
  end
  if changed then L.mix_apply(c, i) end
  return changed
end

-- édition du profil (fenêtre) : écrit la setlist (les autres champs sont gardés)
local SETLIST_ORDER = { "name", "gap_s", "songs", "live", "live_exceptions" }
local function save_profile(c)
  local src = c and c.setlist and L.read(c.setlist)
  local d = src and R.json_decode(src)
  if type(d) ~= "table" then return false end
  local live = R.json_array({})
  for _, r in ipairs(L.ROLES) do if L.mix.live[r[1]] then live[#live + 1] = r[1] end end
  d.live = live
  local exc = {}
  for title, v in pairs(L.mix.exc) do
    local e, any = {}, false
    for role, m in pairs(v) do
      if (m == "live") ~= (L.mix.live[role] == true) then e[role] = m; any = true end
    end
    if any then exc[title] = e end
  end
  d.live_exceptions = exc
  local txt = R.json_encode(d, "  ", SETLIST_ORDER)
  if not R.write_atomic(c.setlist, txt) then return false end
  L.mix.src = L.read(c.setlist)
  return true
end

function L.live_toggle(c, role)
  role = L.norm_role(role)
  if not c or not role then return false end
  L.load_live(c, true)
  L.mix.live[role] = not L.mix.live[role] or nil
  local ok = save_profile(c)
  L.mix_apply(c)
  return ok
end

-- exception du morceau k pour le rôle : nil (profil) → inverse du profil → … (cycle)
function L.live_exc_cycle(c, k, role)
  role = L.norm_role(role)
  local s = c and c.songs[k]
  if not s or not role then return false end
  L.load_live(c, true)
  local e = L.mix.exc[s.title] or {}
  local base = L.mix.live[role] and "live" or "stem"
  if e[role] == nil then e[role] = (base == "live") and "stem" or "live" else e[role] = nil end
  L.mix.exc[s.title] = e
  local ok = save_profile(c)
  L.mix_apply(c)
  return ok
end

-- ---------------------------------------------------------------------------------------
-- ReaCue Studio (page studio.html) : boucle de section, rampe de vitesse, transposition, export audio.
-- La page agit directement sur les pistes par l'API web de REAPER (mute, solo, volume, pan, position) ;
-- ces commandes-ci passent par la télécommande (PIN) car l'API web ne les permet pas.
-- État publié pour la page : ExtState ReaCue/studio = vitesse|transposition|passage|passages|de|à
-- ---------------------------------------------------------------------------------------
function L.loop_section(c, t)
  t = tonumber(t)
  if not c or not t then return false end
  local i = L.song_index(c, t + 0.01)
  local secs = L.song_sections(c, i)
  local k = nil
  for n, x in ipairs(secs) do if math.abs(x.start - t) < 0.05 then k = n end end
  if not k then k = L.section_at(secs, t) end
  if not k then return false end
  L.reh.anchor = nil
  L.loop_set(c, secs[k], secs[k])
  return true
end

-- vitesse du passage `pass` (1 = premier) : paliers réguliers de `from` à `to`, puis `to`
function L.ramp_rate(rp, pass)
  local k = math.min(math.max(pass, 1), rp.n) - 1
  return rp.from + (rp.to - rp.from) * k / math.max(1, rp.n - 1)
end

function L.set_ramp(c, arg)
  arg = arg or ""
  local R_ = L.reh
  if arg == "" then
    if R_.ramp then R_.ramp = nil; if R_.on then L.set_rate(1.0) end end
    L.studio_publish(true)
    return true
  end
  local f, t, n, at = arg:match("^([%d%.]+):([%d%.]+):(%d+):?([%d%.]*)$")
  f, t, n = tonumber(f), tonumber(t), tonumber(n)
  if not f or not t or not n or f < 0.5 or f > 1 or t < 0.5 or t > 1 or n < 2 or n > 32 then return false end
  local rp = { from = f, to = t, n = math.floor(n), pass = 0 }
  if at ~= "" then
    R_.ramp = rp
    if not L.loop_section(c, at) then R_.ramp = nil; return false end   -- 1er passage compté au départ
  else
    if not R_.loop then return false end
    R_.ramp = rp
    rp.pass = 1
    L.set_rate(f)
  end
  L.studio_publish(true)
  return true
end

-- prises audio des pistes musicales (stems) : celles du morceau en cours dans un concert
function L.music_takes(c)
  local out = {}
  local s = c and not c.pseudo and c.songs and c.songs[L.song_index(c, L.pos())] or nil
  for _, tr in ipairs(music_tracks()) do
    for k = 0, (reaper.CountTrackMediaItems and reaper.CountTrackMediaItems(tr) or 0) - 1 do
      local it = reaper.GetTrackMediaItem(tr, k)
      local tk = it and reaper.GetActiveTake(it)
      if tk and not (reaper.TakeIsMIDI and reaper.TakeIsMIDI(tk)) then
        local pos = reaper.GetMediaItemInfo_Value(it, "D_POSITION")
        if not s or (pos >= s.start - 0.05 and pos < (s.stop or s.start) + 0.05) then out[#out + 1] = tk end
      end
    end
  end
  return out
end

function L.transpose_get(c)
  local tk = L.music_takes(c)[1]
  if not tk then return 0 end
  local p = reaper.GetMediaItemTakeInfo_Value(tk, "D_PITCH") or 0
  return math.floor(p + 0.5)
end

-- transposition des stems par REAPER (D_PITCH de chaque prise, mode de pitch par défaut du projet) ;
-- relative : les écarts déjà réglés à la main entre prises sont gardés. Bornée à ±12 demi-tons.
function L.transpose(c, arg)
  local takes = L.music_takes(c)
  if #takes == 0 then return false end
  local cur = L.transpose_get(c)
  local target
  if arg == "0" or arg == "reset" then target = 0 else
    local d = tonumber(arg)
    if not d or d ~= math.floor(d) then return false end
    target = cur + d
  end
  if target < -12 or target > 12 then return false end
  local delta = target - cur
  if delta ~= 0 then
    if reaper.Undo_BeginBlock then reaper.Undo_BeginBlock() end
    for _, tk in ipairs(takes) do
      reaper.SetMediaItemTakeInfo_Value(tk, "D_PITCH", (reaper.GetMediaItemTakeInfo_Value(tk, "D_PITCH") or 0) + delta)
    end
    if reaper.Undo_EndBlock then reaper.Undo_EndBlock(L.lang() == "en" and "ReaCue: transpose" or "ReaCue : transposition", -1) end
    if reaper.UpdateArrange then reaper.UpdateArrange() end
  end
  L.studio_publish(true)
  return true
end

local studio_last, studio_t = nil, -1e9
function L.studio_publish(force, c)
  local now = reaper.time_precise()
  if not force and now - studio_t < 0.25 then return end
  studio_t = now
  local rate = reaper.Master_GetPlayRate and reaper.Master_GetPlayRate(0) or 1
  local rp = L.reh.ramp
  local v = string.format("%.3f|%d|%d|%d|%.2f|%.2f", rate or 1, L.transpose_get(c or L.studio_c),
    rp and math.floor(rp.pass) or 0, rp and math.floor(rp.n) or 0, rp and rp.from or 0, rp and rp.to or 0)
  if v ~= studio_last then
    reaper.SetExtState("ReaCue", "studio", v, false)
    studio_last = v
  end
end

-- fichier source d'une prise (sources « section » / « reverse » remontées)
local function take_file(tk)
  local src = reaper.GetMediaItemTake_Source(tk)
  local parent = reaper.GetMediaSourceParent and reaper.GetMediaSourceParent(src)
  while parent do src = parent; parent = reaper.GetMediaSourceParent(src) end
  return reaper.GetMediaSourceFileName(src, "") or ""
end

local EXPORT_SKIP = { CUES = true, ["TIMECODE LTC"] = true, ["TIMECODE MTC"] = true }

-- pistes et items du projet pour l'export (fichier, position, longueur, décalage, vitesse, volumes, pan)
function L.export_tracks()
  local out = R.json_array({})
  for i = 0, (reaper.CountTracks and reaper.CountTracks(0) or 0) - 1 do
    local tr = reaper.GetTrack(0, i)
    local name = track_name(tr)
    if not EXPORT_SKIP[name] then
      local items = R.json_array({})
      for k = 0, (reaper.CountTrackMediaItems and reaper.CountTrackMediaItems(tr) or 0) - 1 do
        local it = reaper.GetTrackMediaItem(tr, k)
        local tk = it and reaper.GetActiveTake(it)
        if tk and not (reaper.TakeIsMIDI and reaper.TakeIsMIDI(tk)) then
          local file = take_file(tk)
          if file ~= "" then
            items[#items + 1] = {
              file = file,
              position = reaper.GetMediaItemInfo_Value(it, "D_POSITION"),
              length = reaper.GetMediaItemInfo_Value(it, "D_LENGTH"),
              offset = reaper.GetMediaItemTakeInfo_Value(tk, "D_STARTOFFS"),
              rate = reaper.GetMediaItemTakeInfo_Value(tk, "D_PLAYRATE"),
              vol = reaper.GetMediaItemInfo_Value(it, "D_VOL") * reaper.GetMediaItemTakeInfo_Value(tk, "D_VOL"),
            }
          end
        end
      end
      if #items > 0 then
        out[#out + 1] = { name = name, guid = reaper.GetTrackGUID and reaper.GetTrackGUID(tr) or "",
                          vol = reaper.GetMediaTrackInfo_Value(tr, "D_VOL"), pan = reaper.GetMediaTrackInfo_Value(tr, "D_PAN"),
                          items = items }
      end
    end
  end
  return out
end

-- export audio demandé par la page : la demande (JSON) est dans ReaCue/export_req, `id` doit correspondre ;
-- la tâche complète (pistes, items, sélection) est écrite dans ReaCueMCP/export_job.json puis la CLI la traite
function L.studio_export(c, id)
  if type(id) ~= "string" or not id:match("^%w+$") then return false end
  local req = R.json_decode(reaper.GetExtState(REMOTE, "export_req"))
  if type(req) ~= "table" or req.id ~= id then return false end
  reaper.SetExtState(REMOTE, "export_req", "", false)
  local www = reaper.GetResourcePath() .. SEP .. "reaper_www_root"
  local st = R.json_decode(L.read(www .. SEP .. "reacue_export.json") or "")
  if type(st) == "table" and st.state == "running" and st.id ~= id and tonumber(st.time)
     and os.time() - tonumber(st.time) < 300 then
    return false                                -- un autre export tourne encore
  end
  local fn = L.project_file()
  local job = { id = id, request = req, tracks = L.export_tracks(), at = L.pos(), lang = L.lang() }
  if fn ~= "" then
    job.project = fn
    job.project_dir = fn:match("^(.*)[/\\][^/\\]+$")
  end
  if reaper.GetSet_LoopTimeRange then
    local a, b = reaper.GetSet_LoopTimeRange(false, false, 0, 0, false)
    if a and b and b - a > 0.01 then job.selection = R.json_array({ a, b }) end
  end
  local dir = reaper.GetResourcePath() .. SEP .. "ReaCueMCP"
  reaper.RecursiveCreateDirectory(dir, 0)
  local path = dir .. SEP .. "export_job.json"
  if not R.write_atomic(path, R.json_encode(job)) then return false end
  reaper.RecursiveCreateDirectory(www, 0)
  R.write_atomic(www .. SEP .. "reacue_export.json",
    R.json_encode({ id = id, state = "running", progress = 0.02, time = os.time() }))
  local ok = L.run_cli("export", path, "--job")
  return ok and true or false
end

-- ---------------------------------------------------------------------------------------
-- ReaCue Studio, écrans BIBLIO et GROUPE : état durable (étape du parcours, notes de section, temps de
-- lecture), musiciens connectés (prompteurs), « Prêt », « On reprend à… ».
-- État durable : <ressources>/ReaCueMCP/reacue_state.json (lu par reacue_mcp/library.py) :
--   {"version": 1, "songs": {"<clé>": {"title", "stage", "notes": {"<mesure>": "texte"}, "solo_s", "band_s",
--     "days": {"AAAA-MM-JJ": secondes en groupe}, "last"}}}   clé = L.song_key(chemin du .RPP)
-- ---------------------------------------------------------------------------------------
L.STAGES = { new = true, solo = true, band = true, stage = true }
L.MAX_NOTE = 200

function L.url_decode(s)
  s = tostring(s or ""):gsub("+", " ")
  return (s:gsub("%%(%x%x)", function(h) return string.char(tonumber(h, 16)) end))
end
function L.url_encode(s)
  -- RFC 3986 : seuls les octets ASCII non réservés restent littéraux. %w dépend de la locale
  -- et laisse parfois passer un seul octet d'un caractère UTF-8 sur macOS.
  return (tostring(s or ""):gsub("[^A-Za-z0-9%-%._~]", function(c) return string.format("%%%02X", c:byte()) end))
end
function L.song_key(p) return L.lower_utf8((tostring(p or ""):gsub("\\", "/"))) end

function L.state_path() return reaper.GetResourcePath() .. SEP .. "ReaCueMCP" .. SEP .. "reacue_state.json" end
function L.state_load()
  local d = R.json_decode(L.read(L.state_path()) or "")
  if type(d) ~= "table" then d = {} end
  if type(d.songs) ~= "table" or R.is_array(d.songs) then d.songs = {} end
  d.version = 1
  return d
end
function L.state_save(d)
  reaper.RecursiveCreateDirectory(reaper.GetResourcePath() .. SEP .. "ReaCueMCP", 0)
  return R.write_atomic(L.state_path(), R.json_encode(d, " "))
end
local function state_song(d, path, title)
  local k = L.song_key(path)
  local s = d.songs[k]
  if type(s) ~= "table" then s = {}; d.songs[k] = s end
  if title and title ~= "" then s.title = title end
  return s
end

-- projet (.RPP) du morceau i : concert = projet d'origine du morceau, sinon le projet ouvert
function L.song_project(c, i)
  local s = c and c.songs and c.songs[i or 1]
  if c and not c.pseudo and s and s.project then return s.project, s.title end
  return L.project_file(), s and s.title
end

-- note de section : arg = « <n° du morceau>:<mesure de début>:<texte urlencodé> » (texte vide = effacer)
function L.set_note(c, arg)
  local i, bar, txt = tostring(arg or ""):match("^(%d+):(%d+):(.*)$")
  i, bar = tonumber(i), tonumber(bar)
  if not i or not bar or bar < 1 then return false end
  if c and c.songs and not c.songs[i] then return false end
  local proj, title = L.song_project(c, i)
  if not proj or proj == "" then return false end
  txt = L.url_decode(txt):gsub("[%z\1-\31\127]+", " "):gsub("^ +", ""):gsub(" +$", "")
  local chars = utf8.len(txt)
  if not chars then return false end
  if chars > L.MAX_NOTE then txt = txt:sub(1, utf8.offset(txt, L.MAX_NOTE + 1) - 1) end
  local d = L.state_load()
  local s = state_song(d, proj, title)
  if type(s.notes) ~= "table" then s.notes = {} end
  s.notes[tostring(bar)] = txt
  if not L.state_save(d) then return false end
  L.run_cli("notes")                    -- republie les notes dans reacue_song.json (tous les prompteurs)
  return true
end

-- étape du parcours réglée à la main : arg = « <clé ou chemin urlencodé>:<new|solo|band|stage|auto> »
function L.set_stage(arg)
  local key, st = tostring(arg or ""):match("^(.+):(%a+)$")
  if not key or not (L.STAGES[st] or st == "auto") then return false end
  key = L.song_key(L.url_decode(key))
  if not key:match("%.rpp$") then return false end
  local d = L.state_load()
  local s = d.songs[key]
  if type(s) ~= "table" then s = {}; d.songs[key] = s end
  s.stage = (st ~= "auto") and st or nil
  if not L.state_save(d) then return false end
  L.run_cli("library")                  -- reacue_library.json republié
  return true
end

-- « On reprend à… » : lecture une mesure avant le début de la section (temps t de la timeline)
function L.resume_at(c, t)
  t = tonumber(t)
  if not c or not t or t < 0 then return false end
  local i = L.song_index(c, t + 0.01)
  if L.reh.loop then L.loop_off() end
  local t0 = math.max(0, t - L.bar_len_before(t, c.songs[i] and c.songs[i].bpm))
  reaper.SetEditCurPos(t0, true, true)
  if not L.playing() then reaper.OnPlayButton() end
  return true
end

-- musiciens connectés : chaque prompteur écrit toutes les ~2 s ReaCue/hb<0-7> (emplacement tiré de son identifiant)
--   = <id>|<rôle>|<nom urlencodé>|<prêt 0/1>|<époque>        (la fenêtre lit, efface, garde 10 s)
-- publié pour les pages : ReaCue/band = <époque>|<id>,<rôle>,<nom>,<prêt>,<âge s>;…
-- « Prêt » ne compte que s'il porte l'époque en cours : la remise à zéro (readyreset) change d'époque.
L.BAND_TTL, L.BAND_SLOTS, L.BAND_MAX = 10, 8, 16
L.band = { epoch = nil, clients = {}, last = nil, pub_t = -1e9 }
local MUSICIAN = { drums = true, bass = true, guitars = true, lead_guitar = true, vocals = true, keys = true, all = true }

function L.band_epoch()
  if not L.band.epoch then
    local e = reaper.GetExtState(REMOTE, "band_epoch")
    if not e:match("^%w+$") then e = tostring(os.time()); reaper.SetExtState(REMOTE, "band_epoch", e, true) end
    L.band.epoch = e
  end
  return L.band.epoch
end

function L.band_beat(v, now)
  local id, role, name, ready, ep = tostring(v or ""):match("^(%w+)|([%w_]*)|([^|]*)|([01])|(%w*)")
  if not id or #id > 24 then return false end
  name = L.url_decode(name):gsub("[%z\1-\31\127|;,]", " ")
  local chars = utf8.len(name)
  if not chars then return false end
  if chars > 24 then name = name:sub(1, utf8.offset(name, 25) - 1) end
  local B = L.band
  local cur = B.clients[id]
  if not cur then
    local n = 0
    for _ in pairs(B.clients) do n = n + 1 end
    if n >= L.BAND_MAX then return false end
    cur = {}
    B.clients[id] = cur
  end
  local ok = ready == "1" and ep == L.band_epoch()
  cur.role, cur.name, cur.at = role, name, now
  cur.ready_at = ok and (cur.ready and cur.ready_at or now) or nil
  cur.ready = ok
  return true
end

function L.band_reset()
  local e = tostring(os.time())
  if e == L.band_epoch() then e = e .. "b" end
  L.band.epoch = e
  reaper.SetExtState(REMOTE, "band_epoch", e, true)
  for _, cl in pairs(L.band.clients) do cl.ready, cl.ready_at = false, nil end
  L.band_publish(L.band.now or reaper.time_precise(), true)
  return true
end

function L.band_list(now)
  local out = {}
  for id, cl in pairs(L.band.clients) do
    if now - cl.at <= L.BAND_TTL then out[#out + 1] = { id = id, role = cl.role, name = cl.name, ready = cl.ready, age = now - cl.at } end
  end
  table.sort(out, function(a, b) if a.role ~= b.role then return a.role < b.role end return a.id < b.id end)
  return out
end

function L.musicians(now)
  local n = 0
  for _, x in ipairs(L.band_list(now or reaper.time_precise())) do if MUSICIAN[x.role] then n = n + 1 end end
  return n
end

function L.band_publish(now, force)
  local parts = {}
  for id, cl in pairs(L.band.clients) do if now - cl.at > L.BAND_TTL then L.band.clients[id] = nil end end
  for _, x in ipairs(L.band_list(now)) do
    parts[#parts + 1] = string.format("%s,%s,%s,%d,%d", x.id, x.role, L.url_encode(x.name), x.ready and 1 or 0, math.floor(x.age))
  end
  local v = L.band_epoch() .. "|" .. table.concat(parts, ";")
  if force or v ~= L.band.last or now - L.band.pub_t > 1 then
    reaper.SetExtState(REMOTE, "band", v, false)
    L.band.last, L.band.pub_t = v, now
  end
  return v
end

function L.band_poll(now)
  L.band.now = now
  local got = false
  for k = 0, L.BAND_SLOTS - 1 do
    local v = reaper.GetExtState(REMOTE, "hb" .. k)
    if v ~= "" then
      reaper.SetExtState(REMOTE, "hb" .. k, "", false)
      if L.band_beat(v, now) then got = true end
    end
  end
  L.band_publish(now, got)
end

-- temps de lecture par morceau (étape du parcours) : seul ou en groupe (≥ 2 musiciens connectés) ;
-- cumulé en mémoire, écrit dans l'état durable toutes les 30 s et à la fermeture
L.prog = { acc = {}, last = nil, flush_t = nil }
function L.practice_tick(c, now, playing, musicians)
  local P = L.prog
  local last = P.last
  P.last = now
  P.flush_t = P.flush_t or now
  if playing and c and last then
    local dt = now - last
    if dt > 0 and dt < 1 then
      local i = L.song_index(c, L.pos())
      local proj, title = L.song_project(c, i)
      if proj and proj ~= "" then
        local k = L.song_key(proj)
        local a = P.acc[k] or { path = proj, title = title, solo = 0, band = 0 }
        if (musicians or 0) >= 2 then a.band = a.band + dt else a.solo = a.solo + dt end
        P.acc[k] = a
      end
    end
  end
  if now - P.flush_t >= 30 then L.practice_flush(now) end
end

function L.practice_flush(now)
  local P = L.prog
  P.flush_t = now or reaper.time_precise()
  if next(P.acc) == nil then return false end
  local d = L.state_load()
  local day = os.date("%Y-%m-%d")
  for _, a in pairs(P.acc) do
    local s = state_song(d, a.path, a.title)
    s.solo_s = math.floor(((tonumber(s.solo_s) or 0) + a.solo) * 10 + 0.5) / 10
    s.band_s = math.floor(((tonumber(s.band_s) or 0) + a.band) * 10 + 0.5) / 10
    if a.band > 0 then
      if type(s.days) ~= "table" or R.is_array(s.days) then s.days = {} end
      s.days[day] = math.floor(((tonumber(s.days[day]) or 0) + a.band) * 10 + 0.5) / 10
    end
    s.last = os.time()
  end
  P.acc = {}
  return L.state_save(d)
end

-- ouvrir un projet de la bibliothèque (comme l'onglet Concert : nouvel onglet, sauf si c'est le projet en cours)
function L.open_project(p)
  p = tostring(p or "")
  if not L.lower_utf8(p):match("%.rpp$") or not L.exists(p) then return false end
  if L.song_key(L.project_file()) == L.song_key(p) then return true end
  reaper.Main_OnCommand(40859, 0)
  reaper.Main_openProject(p)
  return true
end

function L._reset_remote() seen, seen_list = {}, {}; last_seen_v = nil; L.regie_seen = nil
  L.band = { epoch = nil, clients = {}, last = nil, pub_t = -1e9 }; L.prog = { acc = {}, last = nil, flush_t = nil } end

return L
