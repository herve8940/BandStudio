"""ReaCue Studio, écrans BIBLIO et GROUPE côté REAPER (Lua 5.4 via lupa, API REAPER simulée) : musiciens
connectés (battements de plusieurs téléphones, emplacements, expiration 10 s), « Prêt » (époque, remise à zéro),
notes de section (état durable + CLI « notes »), étape manuelle (CLI « library »), « On reprend à… », temps de
lecture seul / en groupe, ouverture d'un morceau depuis BIBLIO (fenêtre ReaCue), libellé « MORCEAU 2 / 3 »."""
import json
from pathlib import Path
from urllib.parse import quote

import pytest

pytest.importorskip("lupa")

import test_concert_lua as TL  # noqa: E402
import test_reacue_window as TW  # noqa: E402


@pytest.fixture(scope="module")
def concert(tmp_path_factory):
    return TL.make_concert(tmp_path_factory.mktemp("band"))


def rt(concert, tmp_path=None):
    L, g = TW.rt(concert)
    if tmp_path is not None:
        inst = tmp_path / "ReaCue"
        (inst / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
        (inst / ".venv" / "bin" / "python").write_text("")
        g.state.ext["install_dir"] = str(inst)
    return L, g, TL.lib(L)


def send(M, g, c, cmd, arg="", n=[0]):
    n[0] += 1
    g.state.ext["remote"] = f"{cmd}|{arg}|{M.remote_pin()}|b{n[0]}"
    return tuple(M.remote_poll(c))


def band(g):
    v = g.state.ext["band"]
    ep, _, rest = v.partition("|")
    return ep, [e.split(",") for e in rest.split(";") if e]


def test_presence_several_phones_ready_and_expiry(concert):
    L, g, M = rt(concert)
    st = g.state
    st.ext["band_epoch"] = "E1"
    # trois téléphones, emplacements différents, un nom accentué (urlencodé)
    st.ext["hb0"] = "aaaa1111|drums|Max|0|"
    st.ext["hb3"] = "bbbb2222|vocals|L%C3%A9a|1|E1"
    st.ext["hb5"] = "cccc3333|regie||0|"
    M.band_poll(100.0)
    assert st.ext["hb0"] == "" and st.ext["hb3"] == "" and st.ext["hb5"] == ""      # lus puis effacés
    ep, rows = band(g)
    assert ep == "E1" and sorted(r[0] for r in rows) == ["aaaa1111", "bbbb2222", "cccc3333"]
    lea = next(r for r in rows if r[0] == "bbbb2222")
    assert lea[1] == "vocals" and M.url_decode(lea[2]) == "Léa" and lea[3] == "1"
    assert M.musicians(100.0) == 2                                                    # la Régie ne compte pas
    # « Prêt » avec une ancienne époque : ignoré
    st.ext["hb0"] = "aaaa1111|drums|Max|1|OLD"
    M.band_poll(101.0)
    assert next(r for r in band(g)[1] if r[0] == "aaaa1111")[3] == "0"
    st.ext["hb0"] = "aaaa1111|drums|Max|1|E1"
    M.band_poll(102.0)
    assert next(r for r in band(g)[1] if r[0] == "aaaa1111")[3] == "1"
    # même emplacement : deux téléphones l'un après l'autre (un battement perdu est repris au suivant)
    st.ext["hb3"] = "dddd4444|bass||0|"
    M.band_poll(103.0)
    st.ext["hb3"] = "bbbb2222|vocals|L%C3%A9a|1|E1"
    M.band_poll(104.0)
    assert len(band(g)[1]) == 4
    # expiration : plus de signe depuis 10 s
    st.ext["hb0"] = "aaaa1111|drums|Max|1|E1"
    M.band_poll(112.5)
    ids = sorted(r[0] for r in band(g)[1])
    assert ids == ["aaaa1111", "bbbb2222", "dddd4444"]                               # la Régie (100 s) a disparu
    M.band_poll(125.0)
    assert band(g)[1] == []
    # valeurs invalides ignorées
    st.ext["hb1"] = "pas|bon"
    st.ext["hb2"] = "x" * 40 + "|drums||0|"
    M.band_poll(126.0)
    assert band(g)[1] == []


def test_ready_reset_changes_epoch(concert):
    L, g, M = rt(concert)
    st = g.state
    st.ext["band_epoch"] = "E7"
    L.execute("os.time = function() return 1761480000 end")
    st.ext["hb4"] = "aaaa1111|drums|Max|1|E7"
    st.ext["hb6"] = "bbbb2222|bass|Zoé|1|E7"
    M.band_poll(10.0)
    assert [r[3] for r in band(g)[1]] == ["1", "1"]
    assert send(M, g, None, "readyreset") == ("readyreset", "ok")                     # possible sans morceau
    ep, rows = band(g)
    assert ep == "1761480000" and st.persist["band_epoch"] == "1761480000"
    assert [r[3] for r in rows] == ["0", "0"]
    # un téléphone qui n'a pas encore vu la nouvelle époque reste « pas prêt »
    st.ext["hb4"] = "aaaa1111|drums|Max|1|E7"
    M.band_poll(11.0)
    assert next(r for r in band(g)[1] if r[0] == "aaaa1111")[3] == "0"
    st.ext["hb4"] = "aaaa1111|drums|Max|1|1761480000"
    M.band_poll(12.0)
    assert next(r for r in band(g)[1] if r[0] == "aaaa1111")[3] == "1"
    # deux remises à zéro dans la même seconde : époques différentes
    send(M, g, None, "readyreset")
    assert band(g)[0] != "1761480000"


@pytest.mark.parametrize("name", ["Léa", "Zoé", "Àlex — Élodie 🎸", "François à la basse", "東京"])
def test_band_names_roundtrip_as_ascii_percent_encoded_utf8(concert, name):
    _, g, M = rt(concert)
    assert M.url_encode(name) == quote(name, safe="-._~")
    assert M.url_decode(M.url_encode(name)) == name
    g.state.ext["hb0"] = "aaaa1111|vocals|" + quote(name, safe="") + "|0|"
    M.band_poll(10.0)
    published = g.state.ext["band"]
    assert published.isascii()
    assert M.url_decode(band(g)[1][0][2]) == name


def test_band_names_limit_characters_and_reject_invalid_utf8(concert):
    _, g, M = rt(concert)
    name = "É🎸" * 20
    assert M.band_beat("aaaa1111|vocals|" + quote(name, safe="") + "|0|", 10.0)
    assert not M.band_beat("bbbb2222|vocals|%C3%28|0|", 10.0)
    M.band_publish(10.0, True)
    rows = band(g)[1]
    assert len(rows) == 1 and M.url_decode(rows[0][2]) == name[:24]


@pytest.mark.parametrize("path", [
    r"C:\Musique\ÉTÉ\L'ŒUVRE — Zoé 🎸.RPP",
    "/Users/Léa/À bientôt/François.RPP",
    "/Music/Demo Song.RPP",
    "/Music/東京 — MIX.RPP",
])
def test_song_keys_preserve_utf8_and_match_python_for_french_titles(concert, path):
    from reacue_mcp.library import song_key
    _, _, M = rt(concert)
    assert M.song_key(path) == song_key(path)


@pytest.mark.parametrize("name,role", [
    ("Chant", "vocals"), ("CHANT 2", "vocals"), ("Batterie", "drums"),
    ("GUITARES 3", "guitars"), ("CLAVIERS", "keys"), ("VOIX", None), ("Élodie 🎸", None),
])
def test_french_instrument_roles_and_generated_voice_tracks(concert, name, role):
    _, _, M = rt(concert)
    assert M.role_of_track(name) == role
    assert M.lower_utf8(name) == name.lower()
    assert M.norm_role("ChAnT") == "vocals"


def test_notes_saved_in_state_and_republished(concert, tmp_path):
    res = concert[0]
    L, g, M = rt(concert, tmp_path)
    c = M.load_concert()
    text = "À la fin — Élodie 🎸 | crash"
    assert send(M, g, c, "note", f"2:9:{quote(text)}") == ("note", "ok")
    st = json.loads(Path(M.state_path()).read_text(encoding="utf-8"))
    key = M.song_key(c.songs[2].project)
    assert key.endswith("second demo.rpp")
    assert st["songs"][key]["notes"] == {"9": text} and st["songs"][key]["title"] == "Second Demo"
    sh = list(g.state.shell.values())[-1]
    assert "-m reacue_mcp.cli notes" in sh
    # effacer, trop long (coupé à 200 caractères), invalide
    assert send(M, g, c, "note", "2:9:") == ("note", "ok")
    assert send(M, g, c, "note", "1:1:" + quote("é" * 250)) == ("note", "ok")
    st = json.loads(Path(M.state_path()).read_text(encoding="utf-8"))
    assert st["songs"][key]["notes"]["9"] == ""
    assert st["songs"][M.song_key(c.songs[1].project)]["notes"]["1"] == "é" * 200
    assert send(M, g, c, "note", "9:1:x") == ("note", "bad")
    assert send(M, g, c, "note", "abc") == ("note", "bad")
    assert send(M, g, c, "note", "1:1:%C3%28") == ("note", "bad")
    assert res.rpp.exists()


def test_stage_manual_and_resume(concert, tmp_path):
    L, g, M = rt(concert, tmp_path)
    c = M.load_concert()
    p = c.songs[1].project
    assert send(M, g, None, "libstage", quote(p, safe="") + ":band") == ("libstage", "ok")
    st = json.loads(Path(M.state_path()).read_text(encoding="utf-8"))
    assert st["songs"][M.song_key(p)]["stage"] == "band"
    assert "-m reacue_mcp.cli library" in list(g.state.shell.values())[-1]
    assert send(M, g, None, "libstage", quote(p, safe="") + ":auto") == ("libstage", "ok")
    st = json.loads(Path(M.state_path()).read_text(encoding="utf-8"))
    assert "stage" not in st["songs"][M.song_key(p)]
    assert send(M, g, None, "libstage", quote(p, safe="") + ":famous") == ("libstage", "bad")
    assert send(M, g, None, "libstage", "notaproject:band") == ("libstage", "bad")
    # « On reprend à… » : une mesure avant la section, lecture lancée, boucle arrêtée
    secs = M.song_sections(c, 2)
    gs = g.state
    gs.play = 0
    assert send(M, g, c, "resume", f"{secs[2].start:.3f}") == ("resume", "ok")
    bar = M.bar_len_before(secs[2].start, c.songs[2].bpm)
    assert gs.cursor == pytest.approx(secs[2].start - bar) and gs.play == 1
    assert send(M, g, c, "loopsec", f"{secs[1].start:.3f}") == ("loopsec", "ok") and M.reh.loop
    assert send(M, g, c, "resume", f"{secs[3].start:.3f}") == ("resume", "ok")
    assert M.reh.loop is None
    assert send(M, g, None, "resume", "10") == ("resume", "noconcert")
    assert send(M, g, c, "resume", "x") == ("resume", "bad")


def test_practice_time_solo_and_band(concert):
    L, g, M = rt(concert)
    c = M.load_concert()
    L.execute("os.date = function(f) return '2026-10-26' end")
    g.state.cursor = c.songs[1].start + 3
    M.practice_tick(c, 0.0, True, 0)
    t = 0.0
    for _ in range(100):                              # 50 s seul (pas de 0,5 s)
        t += 0.5
        M.practice_tick(c, t, True, 1)
    g.state.cursor = c.songs[3].start + 3
    for _ in range(40):                               # 20 s en groupe sur le 3e morceau
        t += 0.5
        M.practice_tick(c, t, True, 3)
    M.practice_tick(c, t + 5, True, 3)                # saut > 1 s : ignoré
    assert M.practice_flush(t + 5)
    st = json.loads(Path(M.state_path()).read_text(encoding="utf-8"))
    s1 = st["songs"][M.song_key(c.songs[1].project)]
    s3 = st["songs"][M.song_key(c.songs[3].project)]
    assert s1["solo_s"] == pytest.approx(49.5, abs=0.6) and s1.get("band_s", 0) == 0
    assert s3["band_s"] == pytest.approx(20, abs=0.6) and s3["days"] == {"2026-10-26": s3["band_s"]}
    # arrêt : rien n'est compté ; écriture automatique toutes les 30 s
    M.practice_tick(c, t + 10, False, 3)
    M.practice_tick(c, t + 40, False, 3)
    st2 = json.loads(Path(M.state_path()).read_text(encoding="utf-8"))
    assert st2["songs"][M.song_key(c.songs[3].project)]["band_s"] == s3["band_s"]


def test_window_opens_song_from_library_and_publishes(concert, tmp_path):
    res = concert[0]
    L, g = TW.rt(concert)
    inst = tmp_path / "ReaCue"
    (inst / ".venv" / "bin").mkdir(parents=True)
    (inst / ".venv" / "bin" / "python").write_text("")
    g.state.ext["install_dir"] = str(inst)
    g.state.ext["remote_pin"] = "1234"
    L.execute("reaper.Main_openProject = function(p) state.opened = p; PROJFILE = p end")
    TW.open_window(L, g)
    TW.frame(L, g)
    shells = list(g.state.shell.values())
    assert any("-m reacue_mcp.cli library" in s for s in shells)                     # ouverture : bibliothèque
    song = str(res.song_srcs[0].path)
    g.state.ext["remote"] = f"open|{quote(song, safe='')}|1234|op1"
    TW.frame(L, g)
    assert g.state.ext["remote_ack"] == "op1|ok"
    assert g.state.opened == song and 40859 in list(g.state.cmds.values())
    assert any("open-song --project" in s and "Demo Song.RPP" in s for s in g.state.shell.values()), list(g.state.shell.values())
    g.state.ext["remote"] = "open|%2Fnulle%2Fpart.RPP|1234|op2"
    TW.frame(L, g)
    assert g.state.ext["remote_ack"] == "op2|bad"
    # battements des prompteurs lus par la fenêtre, publiés dans ReaCue/band
    g.state.ext["hb2"] = "eeee5555|bass|Sam|0|"
    TW.frame(L, g)
    assert "eeee5555,bass,Sam,0" in g.state.ext["band"]
