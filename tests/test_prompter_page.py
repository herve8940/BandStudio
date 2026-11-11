"""La page du prompteur s'affiche sans erreur console, en français et en anglais (Chromium headless)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytest.importorskip("playwright")
sys.path.insert(0, str(ROOT / "tools"))


def test_page_no_console_errors_fr_en():
    import make_screenshots as M
    try:
        M.run(None, check_only=True)
    except SystemExit as e:
        pytest.fail(str(e))
    except Exception as e:                      # Chromium absent : non bloquant
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium non installé")
        raise


def test_demo_song_is_fictional_and_complete():
    import make_screenshots as M
    for lang in ("fr", "en"):
        s = M.demo_song(lang)
        assert s["title"] == "Demo Song" and s["language"] == lang
        assert len(s["bar_times"]) == s["n_bars"] + s["count_in_bars"] + 1
        assert s["lyrics"] and s["chords"] and s["drums"]["bars"]
    assert M.demo_song("en")["sections"][3]["name"] == "Chorus 1"


def _with_words(song):
    """Paroles du morceau de démo avec des temps de mots fictifs (répartis sur la ligne)."""
    for ln in song["lyrics"]:
        ws = ln["text"].split()
        d = (ln["end"] - ln["t"]) / len(ws)
        ln["words"] = [{"w": w, "t": round(ln["t"] + k * d, 4), "end": round(ln["t"] + (k + 0.8) * d, 4)}
                       for k, w in enumerate(ws)]
    return song


@pytest.mark.parametrize("words", [True, False])
def test_vocals_word_highlight(words):
    """Calage mot par mot : le mot en cours est surligné (span .wd.now), les précédents estompés ;
    sans "words", la ligne reste du texte simple (comportement d'avant)."""
    import make_screenshots as M
    try:
        from playwright.sync_api import sync_playwright
        song = M.demo_song("fr")
        if words:
            _with_words(song)
        ln = next(x for x in song["lyrics"] if len(x["text"].split()) >= 3)
        pos = ln["t"] + 0.55 * (ln["end"] - ln["t"])
        M.FakeReaper.song, M.FakeReaper.pos = song, pos
        srv, base = M.serve()
        errors = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport=M.PHONE)
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(f"{base}/prompteur.html?role=vocals&lang=fr")
                page.wait_for_function("document.getElementById('nowName').textContent !== '—'", timeout=8000)
                page.wait_for_timeout(500)
                n_spans = page.locator("#lyLine .wd").count()
                now = page.locator("#lyLine .wd.now").all_text_contents()
                done = page.locator("#lyLine .wd.done").count()
                line = page.text_content("#lyLine")
                browser.close()
        finally:
            srv.shutdown()
    except Exception as e:                      # Chromium absent : non bloquant
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium non installé")
        raise
    assert not errors, errors
    assert " ".join(line.split()) == " ".join(ln["text"].split())
    if not words:
        assert n_spans == 0
        return
    ws = ln["words"]
    k = max(j for j, w in enumerate(ws) if w["t"] <= pos + 0.03)
    assert n_spans == len(ws) and now == [ws[k]["w"]] and done == k


@pytest.mark.parametrize("secure_api", [False, True])
def test_fullscreen_keeps_screen_on(secure_api):
    """Bouton plein écran : écran gardé allumé (Wake Lock sur page sécurisée, sinon petite vidéo muette en
    boucle, cas de REAPER en http) ; 2e appui : tout est relâché."""
    import make_screenshots as M
    try:
        from playwright.sync_api import sync_playwright
        M.FakeReaper.song, M.FakeReaper.pos = M.demo_song("fr"), 0.0
        srv, base = M.serve()
        errors = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport=M.PHONE)
                page.on("pageerror", lambda e: errors.append(str(e)))
                if secure_api:
                    page.add_init_script("""window.__locks = 0; Object.defineProperty(navigator, 'wakeLock',
                      { value: { request: async () => { window.__locks++; return { release() { window.__locks--; } }; } } });""")
                else:   # comme en http sur le réseau local : pas de Wake Lock
                    page.add_init_script("Object.defineProperty(window, 'isSecureContext', { value: false });")
                page.goto(f"{base}/prompteur.html?role=vocals&lang=fr")
                page.wait_for_function("document.getElementById('nowName').textContent !== '—'", timeout=8000)
                page.click("#fsBtn")
                page.wait_for_timeout(400)
                on = page.evaluate("document.getElementById('fsBtn').classList.contains('on')")
                vid = page.evaluate("(() => { const v = document.getElementById('noSleep'); return v ? !v.paused : null; })()")
                locks = page.evaluate("window.__locks || 0")
                page.click("#fsBtn")
                page.wait_for_timeout(200)
                off = page.evaluate("!document.getElementById('fsBtn').classList.contains('on')")
                vid2 = page.evaluate("(() => { const v = document.getElementById('noSleep'); return v ? !v.paused : null; })()")
                locks2 = page.evaluate("window.__locks || 0")
                browser.close()
        finally:
            srv.shutdown()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium non installé")
        raise
    assert not errors, errors
    assert on and off
    if secure_api:
        assert locks == 1 and locks2 == 0 and vid is None
    else:
        assert vid is True and vid2 is False


# --------------------------------------------------------------------------- style « Studio pro » (étape 2)
WEB = ROOT / "reacue_mcp" / "web"
PAGE_TXT = (WEB / "prompteur.html").read_text(encoding="utf-8")


def test_page_uses_studio_base_and_nothing_external():
    """Même base que ReaCue Studio (jetons, polices embarquées, core.js), aucune ressource externe."""
    import re
    assert '<link rel="stylesheet" href="reacue_studio/base.css">' in PAGE_TXT
    assert '<script src="reacue_studio/core.js"></script>' in PAGE_TXT
    assert not re.search(r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//""", PAGE_TXT, re.I)
    assert not re.search(r"""url\(\s*["']?\s*(?:https?:)?//""", PAGE_TXT, re.I)
    assert not re.search(r"""(?:fetch|import)\(\s*["'`]https?:""", PAGE_TXT)
    assert "googleapis" not in PAGE_TXT and "gstatic" not in PAGE_TXT and "://cdn" not in PAGE_TXT.lower()
    # les fichiers liés existent (publiés avec la page : studio.publish_static, L.STUDIO_FILES, installateur)
    from reacue_mcp import studio
    files = {rel for _, rel in studio.static_files()}
    assert {"reacue_studio/base.css", "reacue_studio/core.js"} <= files


def test_page_strings_fr_en_complete():
    """Chaque texte de la page existe en français et en anglais (mêmes clés, rôles et sous-objets compris)."""
    import re
    fr = PAGE_TXT[PAGE_TXT.index("  fr: {") + 7:PAGE_TXT.index("\n  en: {")]
    en = PAGE_TXT[PAGE_TXT.index("\n  en: {") + 8:PAGE_TXT.index("\n};\nconst params")]
    keys = lambda s: re.findall(r"(?:^\s+|[,{]\s*)(\w+):\s", s, re.M)
    kf, ke = keys(fr), keys(en)
    assert sorted(kf) == sorted(ke), (set(kf) ^ set(ke))
    for k in ("lcdBar", "lcdBpm", "lcdKey", "chord", "bassNote", "nextChord", "chart", "note", "inK", "barsAbbr"):
        assert k in kf, k
    for r in ("drums", "bass", "guitars", "lead_guitar", "vocals", "all", "regie", "light"):
        assert f'data-role="{r}"' in PAGE_TXT and PAGE_TXT.count(f"{r}: [") == 2, r


def test_published_sections_have_notes_field():
    """Données publiées : champ « notes » par section (vide pour l'instant)."""
    from reacue_mcp import prompter
    from reacue_mcp.analysis import Analysis, Section
    a = Analysis(file="/x/demo.wav", duration=45.0, bpm=120.0, beats_per_bar=4, denominator=4, tempo_stable=True,
                 tempo_cv=0.0, beats=[1.0 + 0.5 * k for k in range(81)], downbeats=[1.0 + 2.0 * k for k in range(21)],
                 sections=[Section(0, 8, "A", "Couplet 1"), Section(8, 20, "B", "Refrain 1")])
    tl = {"bpm": 120.0, "tempo_mode": "constant", "count_in_bars": 2, "bar_times": [10.0 + 2.0 * k for k in range(23)]}
    song = prompter.build_song(a, {"file": a.file, "title": "Demo"}, tl)
    assert [s["notes"] for s in song["sections"]] == ["", ""]


def _open(M, role, lang, pos, song=None, studio="", vp=None):
    from playwright.sync_api import sync_playwright
    M.FakeReaper.song, M.FakeReaper.pos, M.FakeReaper.studio = song or M.demo_song(lang), pos, studio
    srv, base = M.serve()
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch()
    except Exception as e:
        pw.stop(); srv.shutdown()
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium non installé")
        raise
    page = browser.new_page(viewport=vp or M.PHONE)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.goto(f"{base}/prompteur.html?role={role}&lang={lang}")
    page.wait_for_function("document.getElementById('nowName').textContent !== '—'", timeout=8000)
    page.wait_for_timeout(500)

    def close():
        browser.close(); pw.stop(); srv.shutdown(); M.FakeReaper.studio = ""
    return page, errors, close


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_lcds_section_note_and_transposition(lang):
    """Afficheurs mesure / tempo / ton, n° de mesure dans la section, note de section ; transposition et
    vitesse publiées par la fenêtre ReaCue (ReaCue/studio) appliquées aux accords, à la grille et au ton."""
    import make_screenshots as M
    note = M.NOTES["Pré-refrain 1"][lang]
    page, errors, close = _open(M, "guitars", lang, M.bar_time(27, 2.6))
    try:
        # Song JSON can finish loading before the first transport poll, especially
        # while the complete audio/browser suite is running on the same machine.
        from playwright.sync_api import expect
        expect(page.locator("#lcdBar")).to_have_text("27.3")
        assert page.text_content("#lcdBar") == "27.3" and page.text_content("#lcdBpm") == "112"
        assert page.text_content("#lcdKey") == "Am" and page.text_content("#secPos") == "3/4"
        assert page.is_visible("#secNote") and page.text_content("#secNoteV") == note
        assert page.text_content("#chCur").startswith("F") and page.text_content("#chNx b") == "G"
        assert page.text_content("#chGrid div.here").endswith("F")
        assert page.text_content("#nextK") == ("Ensuite" if lang == "fr" else "Next")
        assert page.text_content("#countV") == "2"
        # Couplet 1 : pas de note
        M.FakeReaper.pos = M.bar_time(12, 0.5)
        page.wait_for_timeout(400)
        assert not page.is_visible("#secNote")
        # +2 demi-tons, vitesse 90 %
        M.FakeReaper.pos, M.FakeReaper.studio = M.bar_time(27, 2.6), "0.900|2|0|0|0|0"
        page.wait_for_timeout(600)
        assert page.text_content("#chCur").startswith("G") and page.text_content("#chNx b") == "A"
        assert page.text_content("#chGrid div.here").endswith("G")
        assert page.text_content("#lcdKey") == "Bm+2" and page.text_content("#lcdBpm") == "10190 %"
    finally:
        close()
    assert not errors, errors


# rôles musiciens : chaque bouton visible fait au moins 44 × 44 px ; textes principaux contrastés (≥ 4.5:1)
CONTRAST_JS = """sels => {
  const rgb = s => { const m = s.match(/[\\d.]+/g) || [0, 0, 0, 0]; return m.map(Number); };
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const bgOf = el => { for (let e = el; e; e = e.parentElement) { const c = rgb(getComputedStyle(e).backgroundColor);
    if (c.length < 4 || c[3] > 0.5) return c; } return [22, 24, 27]; };
  const out = [];
  for (const sel of sels) for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect(); if (!r.width || !r.height || !el.textContent.trim()) continue;
    const a = lum(rgb(getComputedStyle(el).color)), b = lum(bgOf(el));
    out.push([sel, el.textContent.trim().slice(0, 24), (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)]);
  }
  return out;
}"""
TEXT_SELS = ["#title b", "#roleBtn", "#nowName", "#nowLabel", "#barNum", "#secPos", ".rc-lcd .k", ".rc-lcd .v",
             "#chCurK", "#chCur", "#chNxK", "#chNx b", "#chNx span", "#chGridK", "#chGrid div", "#secNoteK", "#secNoteV",
             ".alert", ".alert small", "#nextK", "#nextName", "#countIn", "#countV", "#countK", "#footL", ".list .row",
             "#lyPrev", "#lyLine", "#lyNext", "#lyWhen", "#dSecK", "#dSecV", "#dSecG", "#dCntK", "#dBeats span",
             "#dPhrase div", "#dEvV", "#dEvK", "#dThen", "#dGridT", ".lanes .lb", "#rSecs button", "#rTitle", "#rSub"]


@pytest.mark.parametrize("role,bar", [("guitars", (27, 2.6)), ("bass", (31, 2.3)), ("vocals", (11, 1.6)),
                                      ("drums", (24, 1.2)), ("lead_guitar", (93, 1.0)), ("all", (30, 0.5))])
def test_stage_targets_and_contrast(role, bar):
    import make_screenshots as M
    page, errors, close = _open(M, role, "fr", M.bar_time(*bar))
    try:
        small = page.eval_on_selector_all(
            "button, #strip", "els => els.filter(e => e.offsetParent).map(e => { const r = e.getBoundingClientRect();"
            " return [e.id || e.textContent.trim().slice(0, 20), r.width, r.height]; }).filter(x => x[1] < 44 || x[2] < 44)")
        ratios = page.evaluate(CONTRAST_JS, TEXT_SELS)
        overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth + 1")
    finally:
        close()
    assert not errors, errors
    assert not small, small
    low = [r for r in ratios if r[2] < 4.5]
    assert ratios and not low, low
    assert not overflow


def test_regie_section_buttons_readable():
    """Régie : sections en couleur, texte noir ou blanc selon la couleur (contraste ≥ 4.5:1)."""
    import make_screenshots as M
    from playwright.sync_api import sync_playwright
    M.FakeReaper.song, M.FakeReaper.pos = M.demo_concert("fr"), 0.0
    srv, base = M.serve()
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as e:
                if "Executable doesn't exist" in str(e):
                    pytest.skip("Chromium non installé")
                raise
            page = browser.new_page(viewport=M.PHONE)
            page.goto(f"{base}/prompteur.html?role=regie&lang=fr")
            page.wait_for_selector("#rSecs button", timeout=8000)
            page.wait_for_timeout(300)
            ratios = page.evaluate(CONTRAST_JS, ["#rSecs button", "#rTitle", "#rSub", ".rbtns button span"])
            small = page.eval_on_selector_all(
                "#regie button", "els => els.filter(e => e.offsetParent).map(e => { const r = e.getBoundingClientRect();"
                " return [e.id || e.textContent.trim(), r.width, r.height]; }).filter(x => x[1] < 44 || x[2] < 44)")
            browser.close()
    finally:
        srv.shutdown()
    assert ratios and not [r for r in ratios if r[2] < 4.5], ratios
    assert not small, small
