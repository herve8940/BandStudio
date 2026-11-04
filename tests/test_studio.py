"""ReaCue Studio : publication de la page et de ses ressources (polices embarquées, aucune ressource externe),
formes d'onde (reacue_peaks.json) et exports audio (WAV / MP3, découpe exacte à l'échantillon, mix sans
écrêtage, plusieurs stems, noms de fichiers, copie web, CLI, serveur MCP). Audio synthétique uniquement."""
import base64
import json
import re
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from reacue_mcp import export as E, studio, prompter, i18n

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "reacue_mcp" / "web"
SR = 44100


# --------------------------------------------------------------------------- page et ressources
def test_static_files_match_lua_manifest():
    """La liste copiée par la fenêtre ReaCue (L.STUDIO_FILES) = les fichiers de reacue_mcp/web (hors prompteur)."""
    lua = (ROOT / "reaper" / "ReaCue_concert_lib.lua").read_text(encoding="utf-8")
    block = re.search(r"L\.STUDIO_FILES = \{(.*?)\n\}", lua, re.S).group(1)
    listed = set(re.findall(r'"([^"]+)"', block))
    actual = {rel for _, rel in studio.static_files()}
    assert listed == actual
    assert {"studio.html", "reacue_studio/core.js", "reacue_studio/base.css"} <= actual


def test_no_external_resources_and_fonts_embedded():
    files = [WEB / "studio.html"] + sorted((WEB / "reacue_studio").glob("*.*"))
    for f in files:
        txt = f.read_text(encoding="utf-8")
        assert not re.search(r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//""", txt, re.I), f
        assert not re.search(r"""url\(\s*["']?\s*(?:https?:)?//""", txt, re.I), f
        assert not re.search(r"""(?:fetch|import)\(\s*["'`]https?:""", txt), f
        assert "googleapis" not in txt and "gstatic" not in txt, f
    css = (WEB / "reacue_studio" / "base.css").read_text(encoding="utf-8")
    for fam in ("IBM Plex Sans", "IBM Plex Mono", "Barlow Condensed"):
        assert f'font-family: "{fam}"' in css
    for url in re.findall(r'url\("([^"]+)"\)', css):
        f = WEB / "reacue_studio" / url
        assert f.exists() and f.read_bytes()[:4] == b"wOF2", url
    for lic in ("OFL-IBM-Plex-Sans.txt", "OFL-IBM-Plex-Mono.txt", "OFL-Barlow-Condensed.txt"):
        t = (WEB / "reacue_studio" / "fonts" / lic).read_text(encoding="utf-8")
        assert "SIL Open Font License" in t and "Version 1.1" in t


def test_third_party_notices_mention_fonts():
    txt = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for w in ("IBM Plex", "Barlow", "SIL Open Font License", "OFL-1.1", "reacue_studio/fonts"):
        assert w in txt, w


def test_page_strings_fr_en_complete():
    js = (WEB / "reacue_studio" / "travail.js").read_text(encoding="utf-8")
    fr = js[js.index("RC.STR.fr = {"):js.index("RC.STR.en = {")]
    en = js[js.index("RC.STR.en = {"):js.index("const T = RC.t")]
    keys = lambda s: set(re.findall(r"(?:^\s+|,\s+)(\w+):\s", s, re.M))
    assert keys(fr) == keys(en) and len(keys(fr)) > 60
    # écrans Concert et Lumière : textes ajoutés (Object.assign) dans les deux langues
    cj = (WEB / "reacue_studio" / "concert.js").read_text(encoding="utf-8")
    cfr = cj[cj.index("Object.assign(RC.STR.fr, {"):cj.index("Object.assign(RC.STR.en, {")]
    cen = cj[cj.index("Object.assign(RC.STR.en, {"):cj.index("const T = RC.t")]
    assert keys(cfr) == keys(cen) and len(keys(cfr)) > 50
    assert not (keys(cfr) & keys(fr)) - {"play", "pause", "next", "prev", "again", "none"}
    # écrans Biblio et Groupe : idem
    more = set()
    for name in ("biblio.js", "groupe.js"):
        bj = (WEB / "reacue_studio" / name).read_text(encoding="utf-8")
        bfr = bj[bj.index("Object.assign(RC.STR.fr, {"):bj.index("Object.assign(RC.STR.en, {")]
        ben = bj[bj.index("Object.assign(RC.STR.en, {"):bj.index("const T = RC.t")]
        assert keys(bfr) == keys(ben) and len(keys(bfr)) > 25, name
        more |= keys(bfr)
    html = (WEB / "studio.html").read_text(encoding="utf-8")
    for k in re.findall(r'data-tt?="(\w+)"', html):
        assert k in keys(fr) | keys(cfr) | more, k


def test_publish_copies_studio(tmp_path):
    song = {"version": 1, "title": "Demo", "id": "x1"}
    out = prompter.publish(song, tmp_path)
    for _, rel in studio.static_files():
        assert (tmp_path / rel).read_bytes() == (WEB / rel).read_bytes(), rel
    assert out["studio"].endswith("studio.html")
    assert studio.publish_static(tmp_path) == []                 # déjà à jour : rien de recopié
    (tmp_path / "reacue_studio" / "core.js").write_text("old", encoding="utf-8")
    assert studio.publish_static(tmp_path) == ["reacue_studio/core.js"]


# --------------------------------------------------------------------------- formes d'onde
def test_item_peaks_position_offset_rate():
    y = np.zeros(SR * 4, np.float32)
    y[int(1.0 * SR)] = 0.8                          # impulsion à 1 s dans la source
    y[int(3.0 * SR)] = -0.5
    lo, hi = studio.item_peaks(y, SR, position=10.0, offset=0.5, rate=1.0, length=None, n=400, hop=0.04)
    # timeline = 10 + (1 - 0.5) = 10.5 s -> case 262 ; 10 + 2.5 = 12.5 s -> case 312
    assert hi.argmax() == int(10.5 / 0.04) and hi.max() == pytest.approx(0.8)
    assert lo.argmin() == int(12.5 / 0.04) and lo.min() == pytest.approx(-0.5)
    lo2, hi2 = studio.item_peaks(y, SR, 10.0, 0.5, 2.0, None, 400, 0.04)      # vitesse x2 : 10.25 s
    assert hi2.argmax() == int(10.25 / 0.04)
    lo3, hi3 = studio.item_peaks(y, SR, 10.0, 0.5, 1.0, length=1.0, n=400, hop=0.04)   # item coupé à 11 s
    assert hi3.max() == pytest.approx(0.8) and lo3.min() == 0.0


def test_encode_decode_peaks_compact():
    lo = np.array([-0.5, -1.0, 0.0], np.float32)
    hi = np.array([0.25, 0.5, 0.0], np.float32)
    data, peak = studio.encode_peaks(lo, hi)
    assert peak == 1.0 and len(base64.b64decode(data)) == 6
    a, b = studio.decode_peaks(data)
    assert np.allclose(a, lo, atol=0.01) and np.allclose(b, hi, atol=0.01)


def _wav(path, y, sr=SR):
    sf.write(str(path), y, sr, subtype="FLOAT")
    return str(path)


def test_build_and_publish_peaks(tmp_path):
    t = np.arange(SR * 3) / SR
    a = _wav(tmp_path / "Song-drums.wav", (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32))
    b = _wav(tmp_path / "Song-bass.wav", np.stack([0.2 * np.sin(2 * np.pi * 55 * t)] * 2, 1).astype(np.float32))
    items = [{"file": a, "position": 2.0, "offset": 0.0, "rate": 1.0, "length": 3.0, "track": "Batterie", "guid": "{A}"},
             {"file": b, "position": 2.0, "offset": 0.0, "rate": 1.0, "length": 3.0, "track": "Basse", "guid": "{B}"},
             {"file": a, "position": 6.0, "offset": 0.0, "rate": 1.0, "length": 1.0, "track": "Batterie", "guid": "{C}"}]
    song = {"id": "abc123", "bar_times": [0.0, 2.0, 4.0, 6.0, 8.0]}
    out = studio.publish_peaks(items, song, tmp_path / "www")
    d = json.loads((tmp_path / "www" / studio.PEAKS_NAME).read_text(encoding="utf-8"))
    assert d["song_id"] == "abc123" and d["hop"] == studio.HOP and d["sr"] == SR
    assert [x["name"] for x in d["tracks"]] == ["Batterie", "Basse"] == out["tracks"]
    assert [x["role"] for x in d["tracks"]] == ["drums", "bass"]
    lo, hi = studio.decode_peaks(d["tracks"][0]["data"])
    cell = lambda s: int(s / studio.HOP)
    assert hi[cell(1.0)] == 0 and hi[cell(3.0)] > 0.9 and hi[cell(5.5)] == 0 and hi[cell(6.5)] > 0.9   # 2 items réunis
    assert len(hi) == d["n"] and d["n"] >= cell(9.0)
    assert "fps" in d["tc"] and "offset_s" in d["tc"]


def test_placed_items_uses_plan_positions():
    items = [{"guid": "{A}", "file": "a.wav", "position": 0.0}, {"guid": "{B}", "file": "b.wav", "position": 1.0}]
    out = studio.placed_items(items, None, [{"guid": "{A}", "position": 4.5}, {"guid": "{B}", "position": 5.5}])
    assert [d["position"] for d in out] == [4.5, 5.5] and items[0]["position"] == 0.0
    one = studio.placed_items(None, {"guid": "{M}", "file": "m.wav", "position": 0.0}, None, {"guid": "{M}", "position": 3.0})
    assert one[0]["position"] == 3.0


def test_peaks_cache_reuses_audio_but_refreshes_metadata(tmp_path, monkeypatch):
    f = _wav(tmp_path / "drums.wav", np.ones(SR, np.float32) * 0.25)
    items = [{"file": f, "position": 0.0, "length": 1.0, "track": "Drums", "guid": "{D}"}]
    www = tmp_path / "www"
    assert not studio.publish_peaks(items, {"id": "first", "bar_times": [0, 2]}, www)["cached"]
    before = json.loads((www / studio.PEAKS_NAME).read_text())
    monkeypatch.setattr(studio, "_read_mono", lambda *a: pytest.fail("unchanged audio decoded again"))
    monkeypatch.setattr(studio, "tc_info", lambda: {"fps": 30, "offset_s": 3600})
    assert studio.publish_peaks(items, {"id": "renamed", "bar_times": [0, 2]}, www)["cached"]
    after = json.loads((www / studio.PEAKS_NAME).read_text())
    assert before["tracks"] == after["tracks"]
    assert after["song_id"] == "renamed" and after["tc"]["fps"] == 30


@pytest.mark.parametrize("change", [
    {"position": 0.1}, {"offset": 0.1}, {"rate": 1.1}, {"length": 0.5},
    {"track": "New name"}, {"guid": "{OTHER}"},
])
def test_peaks_cache_invalidates_placement(tmp_path, change):
    f = _wav(tmp_path / "drums.wav", np.ones(SR, np.float32) * 0.25)
    item = {"file": f, "position": 0.0, "length": 1.0, "track": "Drums", "guid": "{D}"}
    song = {"id": "same", "bar_times": [0, 2]}
    studio.publish_peaks([item], song, tmp_path / "www")
    result = studio.publish_peaks([{**item, **change}], song, tmp_path / "www")
    assert result["cached"] is False


def test_peaks_cache_invalidates_replaced_source_same_size_and_mtime(tmp_path):
    import os
    f = Path(_wav(tmp_path / "drums.wav", np.ones(SR, np.float32) * 0.25))
    items, song = [{"file": str(f), "length": 1.0}], {"id": "same", "bar_times": [0, 2]}
    www = tmp_path / "www"
    studio.publish_peaks(items, song, www)
    st = f.stat()
    replacement = Path(_wav(tmp_path / "new.wav", np.ones(SR, np.float32) * 0.75))
    os.utime(replacement, ns=(st.st_atime_ns, st.st_mtime_ns))
    replacement.replace(f)
    assert f.stat().st_size == st.st_size and f.stat().st_mtime_ns == st.st_mtime_ns
    assert not studio.publish_peaks(items, song, www)["cached"]
    data = json.loads((www / studio.PEAKS_NAME).read_text())
    assert data["tracks"][0]["peak"] == pytest.approx(0.75)


def test_peaks_cache_never_retains_failed_decode(tmp_path, monkeypatch):
    source = tmp_path / "drums.wav"
    source.write_bytes(b"broken audio")
    calls = []
    def fail(path):
        calls.append(path)
        raise OSError("cannot decode")
    monkeypatch.setattr(studio, "_read_mono", fail)
    for _ in range(2):
        assert not studio.publish_peaks([{"file": str(source)}], {"bar_times": [0, 2]}, tmp_path / "www")["cached"]
    assert len(calls) == 2


def test_peaks_cache_rebuilds_corrupt_payload_and_changed_duration(tmp_path):
    f = _wav(tmp_path / "drums.wav", np.ones(SR, np.float32))
    items = [{"file": f, "length": 1.0}]
    www = tmp_path / "www"
    studio.publish_peaks(items, {"bar_times": [0, 2]}, www)
    p = www / studio.PEAKS_NAME
    data = json.loads(p.read_text())
    data["tracks"][0]["data"] = "broken"
    p.write_text(json.dumps(data))
    assert not studio.publish_peaks(items, {"bar_times": [0, 2]}, www)["cached"]
    assert not studio.publish_peaks(items, {"bar_times": [0, 4]}, www)["cached"]


# --------------------------------------------------------------------------- exports
BPM, BPB, CI = 120.0, 4, 2          # mesure = 2 s ; count-in 2 mesures (0-4 s), mesure 1 à 4 s


def demo_song(n_bars=8):
    bt = [k * 2.0 for k in range(n_bars + CI + 1)]
    return {"title": "Démo Étoile", "id": "s1", "bpm": BPM, "beats_per_bar": BPB, "count_in_bars": CI, "n_bars": n_bars,
            "bar_times": bt,
            "sections": [{"name": "Intro", "start_bar": 1, "end_bar": 2}, {"name": "Refrain 1", "start_bar": 3, "end_bar": 6},
                         {"name": "Fin", "start_bar": 7, "end_bar": 8}]}


@pytest.fixture
def stems(tmp_path):
    """Deux stems de 20 s (WAV) : bruit déterministe ; la batterie est calée à 1,5 s avec un décalage de 0,25 s."""
    rng = np.random.default_rng(1)
    d = (rng.uniform(-0.9, 0.9, (SR * 20, 2))).astype(np.float32)
    b = (rng.uniform(-0.9, 0.9, (SR * 20, 1))).astype(np.float32)
    fd = _wav(tmp_path / "drums.wav", d)
    fb = _wav(tmp_path / "bass.wav", b)
    tracks = [{"name": "Batterie", "guid": "{D}", "vol": 0.5, "pan": 0.0,
               "items": [{"file": fd, "position": 1.5, "length": 18.0, "offset": 0.25, "rate": 1.0, "vol": 1.0}]},
              {"name": "Basse", "guid": "{B}", "vol": 1.0, "pan": -1.0,
               "items": [{"file": fb, "position": 0.0, "length": 20.0, "offset": 0.0, "rate": 1.0, "vol": 1.0}]},
              {"name": "CLICK", "guid": "{C}", "vol": 1.0, "pan": 0.0, "items": []}]
    return {"d": d, "b": b, "tracks": tracks, "dir": tmp_path}


def job(st, **req):
    r = {"stems": ["Batterie"], "format": "wav", "range": {"kind": "section", "section": 1}, "mode": "separate"}
    r.update(req)
    return {"id": "job1", "title": "Démo Étoile", "project_dir": str(st["dir"] / "Projet"), "tracks": st["tracks"],
            "song": demo_song(), "request": r}


def test_resolve_range():
    s = demo_song()
    assert E.resolve_range(s, {"kind": "section", "section": 1}) == (8.0, 16.0, "Refrain 1")
    assert E.resolve_range(s, {"kind": "section", "section": "Fin"})[:2] == (16.0, 20.0)
    i18n.set_lang("fr")
    assert E.resolve_range(s, {"kind": "bars", "from": 2, "to": 3}) == (6.0, 10.0, "Mes. 2-3")
    assert E.resolve_range(s, {"kind": "song"})[:2] == (4.0, 20.0)
    assert E.resolve_range(s, {"kind": "selection"}, [1.25, 3.5])[:2] == (1.25, 3.5)
    with pytest.raises(E.ExportError):
        E.resolve_range(s, {"kind": "section", "section": 9})
    with pytest.raises(E.ExportError):
        E.resolve_range(s, {"kind": "selection"}, None)


def test_export_wav_exact_cut(stems, tmp_path):
    www = tmp_path / "www"
    res = E.run_job(job(stems), www)
    f = res["files"][0]
    assert f["name"] == "Démo Étoile - Batterie - Refrain 1.wav"
    assert Path(f["path"]) == stems["dir"] / "Projet" / "exports" / f["name"]
    y, sr = sf.read(f["path"], dtype="float32", always_2d=True)
    assert sr == SR and sf.info(f["path"]).subtype == "PCM_24"
    assert len(y) == round(16.0 * SR) - round(8.0 * SR)
    # échantillon j de la timeline = source[j - round(1.5 sr) + round(0.25 sr)]
    k = round(8.0 * SR) - round(1.5 * SR) + round(0.25 * SR)
    assert np.allclose(y, stems["d"][k:k + len(y)], atol=2 ** -22)          # 24 bits, pas de volume de piste
    # copie web (nom ASCII) + état publié
    web = www / f["url"]
    assert f["url"].startswith("reacue_exports/job1_") and web.read_bytes() == Path(f["path"]).read_bytes()
    assert re.fullmatch(r"[A-Za-z0-9._+-]+", web.name)
    st = json.loads((www / E.STATUS_NAME).read_text(encoding="utf-8"))
    assert st["state"] == "done" and st["id"] == "job1" and st["files"][0]["name"] == f["name"]


def test_export_item_starting_inside_range_is_padded(stems, tmp_path):
    j = job(stems, range={"kind": "selection"})
    j["selection"] = [1.0, 2.0]
    y, _ = sf.read(E.run_job(j, tmp_path / "www")["files"][0]["path"], dtype="float32", always_2d=True)
    n0 = round(1.5 * SR) - round(1.0 * SR)
    assert len(y) == SR and np.all(y[:n0] == 0) and np.allclose(y[n0:], stems["d"][round(0.25 * SR):][:SR - n0], atol=2 ** -22)


def test_export_mix_no_clipping_and_names(stems, tmp_path):
    i18n.set_lang("fr")
    res = E.run_job(job(stems, stems=["Batterie", "Basse"], mode="mix", range={"kind": "bars", "from": 1, "to": 2},
                        click=True), tmp_path / "www")
    assert len(res["files"]) == 1
    f = res["files"][0]
    assert f["name"] == "Démo Étoile - Batterie + Basse + Click - Mes. 1-2.wav"
    y, _ = sf.read(f["path"], dtype="float32", always_2d=True)
    assert len(y) == round(8.0 * SR) - round(4.0 * SR)
    peak = np.max(np.abs(y))
    assert 10 ** (-1.2 / 20) < peak <= 10 ** (-1 / 20) + 1e-4                # ramené à -1 dBFS (pas d'écrêtage)
    # pan -1 sur la basse (fader appliqué au mix) : le canal droit n'a que la batterie et le click
    assert np.max(np.abs(y[:, 1])) < np.max(np.abs(y[:, 0]))


def test_export_separate_several_and_click(stems, tmp_path):
    i18n.set_lang("en")
    try:
        res = E.run_job(job(stems, stems=["Batterie", "Basse"], click=True, range={"kind": "song"}), tmp_path / "www")
    finally:
        i18n.set_lang("fr")
    names = [f["name"] for f in res["files"]]
    assert names == ["Démo Étoile - Batterie.wav", "Démo Étoile - Basse.wav", "Démo Étoile - Click.wav"]
    y, _ = sf.read(res["files"][2]["path"], dtype="float32", always_2d=True)
    assert len(y) == 16 * SR
    on = np.flatnonzero(np.abs(y[:, 0]) > 0.05)
    starts = on[np.r_[True, np.diff(on) > SR // 10]]
    assert len(starts) == 32 and abs(starts[1] - starts[0] - SR // 2) <= 2      # 4 temps par mesure de 2 s


@pytest.mark.skipif(not E.mp3_backend(), reason="MP3 indisponible (soundfile < 0.13 et pas de lameenc)")
@pytest.mark.parametrize("kbps", [128, 320])
def test_export_mp3_bitrate(stems, tmp_path, kbps):
    res = E.run_job(job(stems, format="mp3", kbps=kbps, stems=["Basse"]), tmp_path / "www")
    f = res["files"][0]
    assert f["name"].endswith(".mp3") and f["url"].endswith(".mp3")
    info = sf.info(f["path"])
    assert info.format == "MP3" and info.samplerate == SR
    rate = f["bytes"] * 8 / 8.0 / 1000
    assert abs(rate - kbps) / kbps < 0.08
    y, _ = sf.read(f["path"], dtype="float32", always_2d=True)
    assert abs(len(y) - 8 * SR) < 2000


def test_export_rate_resampled(tmp_path):
    t = np.arange(SR * 4) / SR
    f = _wav(tmp_path / "s.wav", (0.5 * np.sin(2 * np.pi * 100 * t)).astype(np.float32))
    j = {"id": "r1", "title": "T", "project_dir": str(tmp_path), "song": demo_song(),
         "tracks": [{"name": "S", "items": [{"file": f, "position": 4.0, "length": 2.0, "offset": 0.0, "rate": 2.0}]}],
         "request": {"stems": ["S"], "format": "wav", "range": {"kind": "bars", "from": 1, "to": 1}}}
    y, _ = sf.read(E.run_job(j, tmp_path / "www")["files"][0]["path"], dtype="float32", always_2d=True)
    freq = np.argmax(np.abs(np.fft.rfft(y[:, 0]))) * SR / len(y)      # fréquence apparente : x2
    assert len(y) == 2 * SR and abs(freq - 200) < 1


def test_export_errors_and_web_cleanup(stems, tmp_path):
    www = tmp_path / "www"
    with pytest.raises(E.ExportError):
        E.run_job(job(stems, stems=["Tuba"]), www)
    with pytest.raises(E.ExportError):
        E.run_job(job(stems, stems=[]), www)
    for k in range(7):
        j = job(stems, range={"kind": "bars", "from": 1, "to": 1})
        j["id"] = f"j{k}"
        E.run_job(j, www)
    left = {p.name.split("_")[0] for p in (www / E.WEB_DIR_NAME).iterdir()}
    assert left == {f"j{k}" for k in range(7 - E.KEEP_WEB_JOBS, 7)}
    # fichier de tâche illisible : état d'erreur publié pour la page
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(Exception):
        E.run_job_file(bad, www)
    assert json.loads((www / E.STATUS_NAME).read_text(encoding="utf-8"))["state"] == "error"


def test_safe_names():
    assert E.file_name('A/B: "x"', "Gt?r", "Refrain 1", "mp3") == "A B x - Gt r - Refrain 1.mp3"
    assert E.ascii_slug("Démo Étoile - Guitare · moi") == "Demo_Etoile_-_Guitare_moi"


def test_cli_export_job(stems, resdir, tmp_path):
    from reacue_mcp import cli
    j = job(stems)
    j["song"] = None                                     # relu dans reaper_www_root/reacue_song.json
    www = resdir / "reaper_www_root"
    www.mkdir(parents=True, exist_ok=True)
    (www / "reacue_song.json").write_text(json.dumps(demo_song()), encoding="utf-8")
    p = tmp_path / "export_job.json"
    p.write_text(json.dumps(j), encoding="utf-8")
    assert cli.main(["export", "--job", str(p), "--resource-dir", str(resdir)]) == 0
    st = json.loads((www / E.STATUS_NAME).read_text(encoding="utf-8"))
    assert st["state"] == "done" and (www / st["files"][0]["url"]).exists()


def test_mcp_export_via_set_sections(stems, resdir, monkeypatch):
    import asyncio
    from reacue_mcp import server
    items = [{"guid": "{D}", "file": stems["tracks"][0]["items"][0]["file"], "position": 1.5, "offset": 0.25,
              "rate": 1.0, "length": 18.0, "track": "Batterie"},
             {"guid": "{B}", "file": stems["tracks"][1]["items"][0]["file"], "position": 0.0, "offset": 0.0,
              "rate": 1.0, "length": 20.0, "track": "Basse"}]

    async def call(cmd, args=None, timeout=30.0):
        if cmd == "ping":
            return {"bridge": "1.4.0", "project": str(stems["dir"] / "P" / "Démo Étoile.RPP")}
        if cmd == "get_audio_items":
            return {"items": items}
        raise AssertionError(cmd)
    monkeypatch.setattr(server.bridge, "call", call)
    www = resdir / "reaper_www_root"
    www.mkdir(parents=True, exist_ok=True)
    (www / "reacue_song.json").write_text(json.dumps(demo_song()), encoding="utf-8")
    res = asyncio.run(server.set_sections([{"export": {"range": {"kind": "section", "section": "Refrain 1"},
                                                       "format": "wav", "mode": "mix"}}]))
    f = res["export"]["files"]
    assert len(f) == 1 and f[0]["name"] == "Démo Étoile - Batterie + Basse - Refrain 1.wav"
    assert Path(f[0]["path"]).parent == stems["dir"] / "P" / "exports"
    bad = asyncio.run(server.set_sections([{"export": {"stems": ["Tuba"]}}]))
    assert "error" in bad
