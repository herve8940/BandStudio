-- ReaCue : éléments d'interface de la fenêtre ReaCue (gfx) : thème « Studio pro » (couleurs, polices), textes,
-- boutons, afficheurs LCD, voyants, icônes, double appui, appui long. Aucun accès au projet ici.
-- ReaCue: UI kit of the ReaCue window (gfx): “Studio pro” theme (colours, fonts), text, buttons, LCD readouts,
-- LEDs, icons, double tap, long press.

local U = {}

-- thème « Studio pro » (même palette que ReaCue Studio, reacue_mcp/web/reacue_studio/base.css) ------------------
-- Toutes les couleurs de la fenêtre viennent d'ici : les onglets n'utilisent que U.<NOM> (pas de RVB en dur).
-- Les fenêtres gfx n'ont ni ombres ni arrondis fins : bords nets (rectangles, filets de 1 px).
U.THEME = {
  bg = { 0x15, 0x17, 0x19 },      -- fond
  panel = { 0x20, 0x23, 0x26 },   -- panneaux, en-tête, ligne d'aide
  inset = { 0x10, 0x12, 0x14 },   -- zones encastrées (afficheurs LCD, bandeau, listes)
  well = { 0x13, 0x15, 0x17 },    -- creux (barre d'onglets, pastilles)
  edge = { 0x0C, 0x0D, 0x0F },    -- bordures sombres
  raise = { 0x2B, 0x2F, 0x35 },   -- boutons, reliefs
  row = { 0x22, 0x26, 0x2B },     -- blocs à venir (setlist, sections)
  slate = { 0x4A, 0x53, 0x61 },   -- bord des blocs sans couleur
  now = { 0x3A, 0x2A, 0x1E },     -- bloc / ligne en cours
  done = { 0x14, 0x16, 0x19 },    -- bloc joué
  ink = { 0xE6, 0xE8, 0xEB },     -- texte
  ink2 = { 0xB4, 0xBA, 0xC2 },    -- texte secondaire clair
  mute = { 0x8A, 0x90, 0x99 },    -- gris (étiquettes)
  dim = { 0x5E, 0x64, 0x6C },     -- gris sombre (éteint)
  sig = { 0xFF, 0x87, 0x37 },     -- orange : action principale, sélection, en cours
  led = { 0x30, 0xDF, 0x75 },     -- vert LED : lecture, OK
  lcd = { 0xF2, 0xC2, 0x30 },     -- jaune LCD : afficheurs, attention
  smpte = { 0x8F, 0xD1, 0xFF },   -- bleu : timecode, bascule active
  red = { 0xFF, 0x4D, 0x4D },     -- erreur
}
local TH = U.THEME
-- noms utilisés par les onglets (rôle -> couleur du thème)
U.BG, U.PANEL2, U.INSET, U.WELL, U.EDGE = TH.bg, TH.panel, TH.inset, TH.well, TH.edge
U.PANEL = TH.raise              -- boutons et barres en relief
U.ROW, U.SLATE, U.NOW, U.DONE = TH.row, TH.slate, TH.now, TH.done
U.INK, U.INK2, U.MUTED, U.GREY = TH.ink, TH.ink2, TH.mute, TH.dim
U.SIG, U.LED, U.LCD, U.SMPTE = TH.sig, TH.led, TH.lcd, TH.smpte
U.ACCENT = TH.led               -- état OK, progression, voyant
U.BLUE = TH.smpte               -- information, tâche en cours
U.WARN = TH.lcd                 -- attention, double appui armé
U.RED = TH.red
U.DARK = TH.bg                  -- texte sur fond clair ou coloré

-- polices : texte (système), afficheurs LCD (monospace), titres (condensée grasse) -----------------------------
-- La première police installée de la liste est retenue ; sinon la dernière (repli toujours présent).
U.FONTS = {
  mac = { sans = { "IBM Plex Sans", "Helvetica" }, mono = { "IBM Plex Mono", "Menlo", "Monaco", "Courier New" },
          cond = { "Barlow Condensed", "Avenir Next Condensed", "Helvetica Neue Condensed Bold", "Arial Narrow", "Arial" } },
  win = { sans = { "IBM Plex Sans", "Arial" }, mono = { "IBM Plex Mono", "Consolas", "Lucida Console", "Courier New" },
          cond = { "Barlow Condensed", "Arial Narrow", "Bahnschrift SemiCondensed", "Arial" } },
}
local SLOT = { sans = 1, mono = 2, cond = 3 }
U.FONT = "Helvetica"
local platform, faces = "mac", {}
function U.init(is_windows)
  platform = is_windows and "win" or "mac"
  faces = {}
  U.FONT = U.FONTS[platform].sans[1]
end

-- une police absente est remplacée par la police par défaut : même largeur qu'un nom inexistant
local PROBE, NOFONT = "MWmw il1 0:É", "ReaCue-no-such-font"
local function installed(face)
  gfx.setfont(SLOT.cond, NOFONT, 40, 0)
  local w0 = gfx.measurestr(PROBE)
  gfx.setfont(SLOT.cond, face, 40, 0)
  local w1 = gfx.measurestr(PROBE)
  if (w0 or 0) <= 0 and (w1 or 0) <= 0 then return nil end      -- pas encore de fenêtre : on ne sait pas
  return math.abs((w1 or 0) - (w0 or 0)) > 0.5
end

-- police retenue pour kind ("sans", "mono", "cond")
function U.face(kind)
  kind = SLOT[kind] and kind or "sans"
  if faces[kind] then return faces[kind] end
  local list = U.FONTS[platform][kind]
  if #list == 1 then faces[kind] = list[1] return list[1] end
  for i = 1, #list - 1 do
    local ok = installed(list[i])
    if ok == nil then return list[#list] end
    if ok then faces[kind] = list[i] return list[i] end
  end
  faces[kind] = list[#list]
  return faces[kind]
end
function U.reset_fonts() faces = {} end

local function setfont(size, bold, kind)
  kind = SLOT[kind] and kind or "sans"
  if kind == "cond" then bold = true end
  gfx.setfont(SLOT[kind], U.face(kind), size, bold and string.byte("b") or 0)
end

-- majuscules (titres) : accents français compris
local UP = { ["à"] = "À", ["â"] = "Â", ["ä"] = "Ä", ["á"] = "Á", ["ç"] = "Ç", ["é"] = "É", ["è"] = "È", ["ê"] = "Ê",
  ["ë"] = "Ë", ["î"] = "Î", ["ï"] = "Ï", ["í"] = "Í", ["ô"] = "Ô", ["ö"] = "Ö", ["ó"] = "Ó", ["ù"] = "Ù", ["û"] = "Û",
  ["ü"] = "Ü", ["ú"] = "Ú", ["ÿ"] = "Ÿ", ["ñ"] = "Ñ", ["æ"] = "Æ", ["œ"] = "Œ" }
function U.upper(s)
  -- string.upper/%s dépendent de la locale C et peuvent traiter séparément les octets UTF-8.
  -- Sur certains macOS, upper("—") corrompt le tiret et %s coupe le second octet de « à ».
  s = tostring(s or ""):gsub("[a-z]", function(c) return string.char(c:byte() - 32) end)
  return (s:gsub("[\xC3\xC5][\x80-\xBF]", function(c) return UP[c] or c end))
end

function U.rgb(r, g, b, a) gfx.set(r / 255, g / 255, b / 255, a or 1) end
function U.set(c, a) U.rgb(c[1], c[2], c[3], a) end

-- font : nil (texte), "mono" (afficheurs), "cond" (titres, toujours en gras)
function U.text(s, x, y, size, c, bold, font)
  setfont(size, bold, font)
  U.set(c or U.INK)
  gfx.x, gfx.y = x, y
  gfx.drawstr(s)
end

function U.text_w(s, size, bold, font)
  setfont(size, bold, font)
  return (gfx.measurestr(s))
end

-- cadre net de 1 px
function U.frame(x, y, w, h, c, a)
  U.set(c or U.EDGE, a)
  gfx.rect(x, y, w, h, 0)
end

-- panneau : fond + bordure sombre
function U.panel(x, y, w, h, fill)
  U.set(fill or U.PANEL2); gfx.rect(x, y, w, h, 1)
  U.frame(x, y, w, h)
  U.set(U.INK, 0.025); gfx.line(x + 1, y + 1, x + w - 2, y + 1)
end

-- afficheur LCD : étiquette en petites capitales, valeur monospace (jaune ; bleu pour le timecode)
-- renvoie la largeur utilisée (w si donné)
function U.lcd(label, value, x, y, w, h, col, vsize)
  vsize = vsize or 20
  local vw = U.text_w(value, vsize, false, "mono")
  w = w or math.max(vw, U.text_w(U.upper(label), 9)) + 24
  U.set(U.INSET); gfx.rect(x, y, w, h, 1)
  U.frame(x, y, w, h)
  U.text(U.upper(label), x + 10, y + 5, 9, U.MUTED)
  local shown = U.fit(tostring(value), math.max(1, w - 20), vsize, false, "mono")
  U.text(shown, x + 10, y + h - vsize - 6, vsize, col or U.LCD, false, "mono")
  return w
end

-- titre en majuscules condensées
function U.title(s, x, y, size, c)
  U.text(U.upper(s), x, y, size or 22, c or U.INK, true, "cond")
end

-- voyant (pastille ronde)
function U.led(x, y, r, c, on)
  U.set(on == false and U.GREY or (c or U.LED)); gfx.circle(x, y, r, 1, 1)
end

-- texte coupé à la largeur w (avec « … »), sans couper un caractère UTF-8
-- chemin trop long : début remplacé par « … » (la fin, le dossier, reste lisible) ; prefix gardé en entier
function U.fit_path(prefix, path, w, size, bold)
  prefix, path = tostring(prefix or ""), tostring(path or "")
  if U.text_w(prefix .. path, size, bold) <= w then return prefix .. path end
  while #path > 1 and U.text_w(prefix .. "…" .. path, size, bold) > w do
    path = path:sub((utf8.offset(path, 2) or 2))
  end
  return prefix .. "…" .. path
end

-- U.on_cut(s) : appelé quand un texte est coupé (tests : aucun libellé coupé dans les captures)
function U.fit(s, w, size, bold, font)
  s = tostring(s or "")
  if U.text_w(s, size, bold, font) <= w then return s end
  if U.on_cut then U.on_cut(s) end
  while #s > 1 and U.text_w(s .. "…", size, bold, font) > w do
    local cut = utf8.offset(s, -1) or #s
    s = s:sub(1, math.max(1, cut - 1))
  end
  return s .. "…"
end

-- souris ------------------------------------------------------------------------------
-- clicked : appui gauche (front montant) ; released : relâchement ; long_id : appui long en cours déclenché
U.clicked, U.released, U.right = false, false, false
U.hover = nil
local prev_cap = 0
local press = nil            -- {id, t, fired}

function U.frame_begin(now)
  local cap = gfx.mouse_cap or 0
  U.clicked = (cap & 1) == 1 and (prev_cap & 1) == 0
  U.released = (cap & 1) == 0 and (prev_cap & 1) == 1
  U.right = (cap & 2) == 2 and (prev_cap & 2) == 0
  U.down = (cap & 1) == 1
  prev_cap = cap
  U.hover = nil
  U.hover_tip = nil
  U.now = now or (reaper.time_precise and reaper.time_precise() or 0)
  U.wheel = gfx.mouse_wheel or 0
  gfx.mouse_wheel = 0
end

function U.over(x, y, w, h)
  local mx, my = gfx.mouse_x, gfx.mouse_y
  return mx >= x and mx < x + w and my >= y and my < y + h
end

-- bouton ; style : nil, "primary" (orange), "on" (bascule active : clair), "warn" / "armed" (jaune), "ghost" (encastré)
local STYLE = {
  primary = { "sig", "dark" }, on = { "ink", "dark" }, warn = { "lcd", "dark" }, armed = { "lcd", "dark" },
  ghost = { "inset", "ink" },
}
local function style_cols(style)
  if style == true then style = "primary" end
  local s = STYLE[style]
  if not s then return U.PANEL, U.INK end
  local fill = ({ sig = U.SIG, ink = U.INK, lcd = U.WARN, inset = U.INSET })[s[1]]
  return fill, s[2] == "dark" and U.DARK or U.INK
end
U.style_cols = style_cols

function U.button(id, label, x, y, w, h, style, size)
  local over = U.over(x, y, w, h)
  if over then U.hover = id end
  local fill, ink = style_cols(style)
  U.set(fill); gfx.rect(x, y, w, h, 1)
  if over then U.set(ink == U.DARK and U.DARK or U.INK, 0.1); gfx.rect(x, y, w, h, 1) end
  U.frame(x, y, w, h, over and U.MUTED or U.EDGE, over and 0.7 or 1)
  size = size or (h <= 28 and 13 or 15)
  local bold = style == "primary" or style == true or style == "on"
  local face = h >= 38 and "cond" or "sans"
  label = U.fit(label, w - 10, size, bold, face)
  local tw = U.text_w(label, size, bold, face)
  U.text(label, x + (w - tw) / 2, y + (h - size) / 2 - 1, size, ink, bold, face)
  return over and U.clicked
end

-- bouton à appui court / appui long : renvoie "click" (relâché avant 0,6 s) ou "long" (une fois)
function U.press_button(id, label, x, y, w, h, col, dim, sub)
  local over = U.over(x, y, w, h)
  if over then U.hover = id end
  if over and U.clicked then press = { id = id, t = U.now, fired = false } end
  local res = nil
  if press and press.id == id then
    if U.down and not press.fired and U.now - press.t >= 0.6 then press.fired = true; res = "long" end
    if U.released then
      if not press.fired and over then res = "click" end
      press = nil
    end
  end
  U.set(col, dim and 0.22 or (over and 1 or 0.88)); gfx.rect(x, y, w, h, 1)
  U.frame(x, y, w, h, over and U.INK or U.EDGE, over and 0.6 or 1)
  local ink = dim and U.MUTED or U.DARK
  local lab = U.fit(label, w - 8, 13, not dim)
  local lw = U.text_w(lab, 13, not dim)
  U.text(lab, x + (w - lw) / 2, y + (sub and 5 or (h - 13) / 2 - 1), 13, ink, not dim)
  if sub then
    local s2 = U.fit(sub, w - 6, 11)
    local sw = U.text_w(s2, 11)
    U.text(s2, x + (w - sw) / 2, y + h - 16, 11, ink)
  end
  if dim then U.set(U.MUTED, 0.6); gfx.line(x + 6, y + h / 2, x + w - 7, y + h / 2) end
  return res
end

-- icônes dessinées (pas de dépendance aux polices) -----------------------------------
local function tri_right(x, y, s) gfx.triangle(x, y - s, x, y + s, x + s * 1.6, y) end
local function tri_left(x, y, s) gfx.triangle(x + s * 1.6, y - s, x + s * 1.6, y + s, x, y) end

function U.icon(kind, cx, cy, s)
  if kind == "play" then tri_right(cx - s * 0.7, cy, s)
  elseif kind == "pause" then gfx.rect(cx - s * 0.9, cy - s, s * 0.65, s * 2, 1); gfx.rect(cx + s * 0.25, cy - s, s * 0.65, s * 2, 1)
  elseif kind == "stop" then gfx.rect(cx - s * 0.85, cy - s * 0.85, s * 1.7, s * 1.7, 1)
  elseif kind == "next" then tri_right(cx - s * 1.3, cy, s * 0.8); tri_right(cx, cy, s * 0.8); gfx.rect(cx + s * 1.3, cy - s * 0.8, s * 0.3, s * 1.6, 1)
  elseif kind == "prev" then gfx.rect(cx - s * 1.6, cy - s * 0.8, s * 0.3, s * 1.6, 1); tri_left(cx - s * 1.3, cy, s * 0.8); tri_left(cx, cy, s * 0.8)
  elseif kind == "home" then gfx.rect(cx - s * 1.2, cy - s, s * 0.3, s * 2, 1); tri_left(cx - s * 0.8, cy, s)
  elseif kind == "up" then gfx.triangle(cx - s, cy + s * 0.5, cx + s, cy + s * 0.5, cx, cy - s * 0.7)
  elseif kind == "down" then gfx.triangle(cx - s, cy - s * 0.5, cx + s, cy - s * 0.5, cx, cy + s * 0.7)
  elseif kind == "left" then gfx.triangle(cx + s * 0.5, cy - s, cx + s * 0.5, cy + s, cx - s * 0.7, cy)
  elseif kind == "right" then gfx.triangle(cx - s * 0.5, cy - s, cx - s * 0.5, cy + s, cx + s * 0.7, cy)
  elseif kind == "x" then
    for d = -1, 1 do gfx.line(cx - s + d, cy - s, cx + s + d, cy + s); gfx.line(cx - s + d, cy + s, cx + s + d, cy - s) end
  elseif kind == "plus" then gfx.rect(cx - s, cy - 1, s * 2, 3, 1); gfx.rect(cx - 1, cy - s, 3, s * 2, 1)
  end
end

-- petit bouton carré à icône
function U.ibutton(id, kind, x, y, w, h, style)
  local over = U.over(x, y, w, h)
  if over then U.hover = id end
  if style == "warn" then U.set(U.WARN, 1) else U.set(U.PANEL, 1) end
  gfx.rect(x, y, w, h, 1)
  if over then U.set(U.INK, 0.1); gfx.rect(x, y, w, h, 1) end
  U.frame(x, y, w, h, over and U.MUTED or U.EDGE)
  U.set(style == "warn" and U.DARK or U.INK)
  U.icon(kind, x + w / 2, y + h / 2, math.min(w, h) / 4.5)
  return over and U.clicked
end

-- bouton de transport : icône + libellé ; style : "primary" (lecture / pause : vert LED), "armed" ou nil
-- grand bouton (h >= 44) : icône + libellé en capitales condensées
function U.tbutton(id, kind, label, x, y, w, h, style, again)
  local over = U.over(x, y, w, h)
  if over then U.hover = id end
  local fill = (style == "armed" and U.WARN) or (style == "primary" and U.LED) or U.PANEL
  U.set(fill); gfx.rect(x, y, w, h, 1)
  if over then U.set(style and U.DARK or U.INK, 0.1); gfx.rect(x, y, w, h, 1) end
  U.frame(x, y, w, h, over and U.MUTED or U.EDGE)
  local ink = style and U.DARK or U.INK
  local big = h >= 44
  local s = big and math.min(10, h / 6) or math.min(7, h / 4.2)
  U.set(ink)
  if big then
    U.icon(kind, x + w / 2, y + h * 0.36, s)
    local lab = U.upper(style == "armed" and again or label)
    local size = w < 80 and 12 or 14
    lab = U.fit(lab, w - 6, size, true, "cond")
    local lw = U.text_w(lab, size, true, "cond")
    U.text(lab, x + (w - lw) / 2, y + h - size - 7, size, ink, true, "cond")
  else
    if style == "armed" then
      local lw = U.text_w(again, 11, true)
      U.text(again, x + (w - lw) / 2, y + (h - 11) / 2 - 1, 11, ink, true)
    else
      U.icon(kind, x + w / 2, y + h / 2, s)
    end
  end
  return over and U.clicked
end

-- double appui (pendant la lecture) -------------------------------------------------------
U.armed = nil
-- vrai au 2e appui dans les 2 s si need, sinon tout de suite
function U.confirm(id, need)
  if not need then U.armed = nil return true end
  if U.armed and U.armed.id == id and U.now - U.armed.t <= 2 then U.armed = nil return true end
  U.armed = { id = id, t = U.now }
  return false
end

function U.is_armed(id) return U.armed ~= nil and U.armed.id == id and U.now - U.armed.t <= 2 end
function U.armed_style(id, default) if U.is_armed(id) then return "armed" end return default end
function U.tick_armed() if U.armed and U.now - U.armed.t > 2 then U.armed = nil end end

-- pastille d'état (alignée à droite sur x) : voyant + libellé en capitales, fond encastré
function U.pill(lab, col, x, y)
  lab = U.upper(lab)
  local w = U.text_w(lab, 15, true, "cond") + 34
  U.set(U.INSET); gfx.rect(x - w, y, w, 26, 1)
  U.frame(x - w, y, w, 26)
  U.set(col); gfx.circle(x - w + 13, y + 13, 5, 1, 1)
  U.text(lab, x - w + 24, y + 5, 15, col, true, "cond")
  return w
end

-- pastille cliquable (état du morceau) : ok = vert, false = gris, "warn" = jaune, "bad" = rouge ; renvoie largeur, clic
function U.chip(id, lab, ok, x, y, size)
  size = size or 12
  local w = U.text_w(lab, size, true) + 26
  local h = size + 12
  local over = U.over(x, y, w, h)
  if over then U.hover = id end
  local col = ok == true and U.ACCENT or (ok == "warn" and U.WARN or (ok == "bad" and U.RED or U.GREY))
  U.set(over and U.PANEL or U.WELL); gfx.rect(x, y, w, h, 1)
  U.frame(x, y, w, h, over and col or U.EDGE, over and 0.9 or 1)
  U.set(col); gfx.circle(x + 10, y + h / 2, 3.5, 1, 1)
  U.text(lab, x + 18, y + 6, size, ok == true and U.INK or (ok == false and U.MUTED or col), true)
  return w, over and U.clicked
end

-- aide au survol d'une zone sans bouton (bande de structure, lignes)
function U.tip(x, y, w, h, text, id)
  if U.over(x, y, w, h) then
    U.hover_tip = text
    if id then U.hover = id end
    return true
  end
  return false
end

-- titre de bloc (« 1. Préparer ») : capitales, gris
function U.heading(s, x, y) U.text(U.upper(s), x, y, 11, U.MUTED, true) end

-- texte sur plusieurs lignes, coupé à la largeur w ; renvoie la hauteur utilisée
function U.para(s, x, y, w, size, col, max_lines)
  size = size or 13
  local lh = size + 5
  local n = 0
  for line in (tostring(s or "") .. "\n"):gmatch("(.-)\n") do
    local words, cur = {}, ""
    for word in line:gmatch("[^ \t\r\n\v\f]+") do
      -- ponctuation française : « » : ; ! ? jamais seuls en début ou en fin de ligne
      local prev = words[#words]
      if prev and (word:sub(1, 2) == "»" or word:match("^[:;!?%)]") or prev:sub(-2) == "«" or prev:sub(-1) == "(") then
        words[#words] = words[#words] .. " " .. word
      else
        words[#words + 1] = word
      end
    end
    if #words == 0 then n = n + 1 end
    for _, wd in ipairs(words) do
      local try = cur == "" and wd or (cur .. " " .. wd)
      if U.text_w(try, size) > w and cur ~= "" then
        if not max_lines or n < max_lines then U.text(cur, x, y + n * lh, size, col) end
        n = n + 1
        cur = wd
      else
        cur = try
      end
    end
    if cur ~= "" then
      if not max_lines or n < max_lines then U.text(cur, x, y + n * lh, size, col) end
      n = n + 1
    end
  end
  if max_lines and n > max_lines then
    if U.on_cut then U.on_cut(s) end
    n = max_lines
  end
  return n * lh
end

return U
