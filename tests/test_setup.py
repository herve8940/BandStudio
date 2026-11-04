"""Installateur commun (install/reacue_setup.py) : idempotence, REAPER, Claude Desktop."""
import json
import subprocess
from pathlib import Path

import pytest

import reacue_setup as S

ROOT = Path(__file__).resolve().parents[1]
AUTHOR_SCR = 'SCR 4 0 RS5a8c1f "Custom: ReaCue_Preparer.lua" "/Users/someone/Documents/reacue-mcp/reaper/ReaCue_Preparer.lua"'


@pytest.fixture
def reaper(tmp_path):
    r = tmp_path / "REAPER"
    (r / "Scripts").mkdir(parents=True)
    return r


def run_install(reaper, lang="fr", mcp="no", running="no", install_dir=ROOT, monkeypatch=None):
    return S.main(["install", "--lang", lang, "--install-dir", str(install_dir), "--reaper-dir", str(reaper),
                   "--mcp", mcp, "--reaper-running", running])


def test_install_is_idempotent(reaper, capsys):
    (reaper / "Scripts" / "__startup.lua").write_text("-- mon script\nreaper.ShowConsoleMsg('x')", encoding="utf-8")
    (reaper / "reaper-kb.ini").write_bytes(b"KEY 1 65 40001 0\r\nACT 0 0 \"x\" \"y\" 1\r\n")
    for _ in range(3):
        assert run_install(reaper) == 0
    st = (reaper / "Scripts" / "__startup.lua").read_text(encoding="utf-8")
    assert st.count("ReaCue_Bridge.lua") == 1 and st.startswith("-- mon script\n")
    kb = (reaper / "reaper-kb.ini").read_bytes().decode()
    assert kb.count("REACUE_PREPARE") == 1 and kb.count("REACUE_PUBLISH") == 1
    assert "\r\n" in kb and "\n" not in kb.replace("\r\n", "")          # fins de ligne Windows conservées
    assert kb.startswith("KEY 1 65 40001 0\r\nACT 0 0")
    assert 'SCR 4 0 REACUE_PREPARE "Custom: ReaCue - Préparer le morceau" "ReaCue/ReaCue_Preparer.lua"' in kb
    for f in S.SCRIPT_FILES:
        assert (reaper / "Scripts" / "ReaCue" / f).read_bytes() == (ROOT / "reaper" / f).read_bytes()
    data = reaper / "ReaCueMCP"
    assert (data / "reacue_install.txt").read_text(encoding="utf-8").strip() == str(ROOT)
    s = json.loads((data / "reacue_settings.json").read_text(encoding="utf-8"))
    assert s["language"] == "fr" and s["count_in_bars"] == 2 and s["count_lang"] == "en"
    assert "Installation terminée" in capsys.readouterr().out


def test_existing_author_startup_line_not_duplicated(reaper):
    line = 'dofile(reaper.GetResourcePath() .. "/Scripts/ReaCue/ReaCue_Bridge.lua") -- ReaCue MCP\n'
    (reaper / "Scripts" / "__startup.lua").write_text(line, encoding="utf-8")
    run_install(reaper)
    assert (reaper / "Scripts" / "__startup.lua").read_text(encoding="utf-8") == line


def test_author_actions_kept_not_duplicated(reaper, capsys):
    (reaper / "reaper-kb.ini").write_text(AUTHOR_SCR + "\n", encoding="utf-8")
    run_install(reaper)
    kb = (reaper / "reaper-kb.ini").read_text(encoding="utf-8")
    assert AUTHOR_SCR in kb and "REACUE_PREPARE" not in kb and "REACUE_PUBLISH" in kb
    assert "autre emplacement" in capsys.readouterr().out


def test_settings_language_update_keeps_user_values(reaper):
    run_install(reaper, "fr")
    p = reaper / "ReaCueMCP" / "reacue_settings.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["count_in_bars"] = 1
    d["announce_voice"] = "Amélie"
    p.write_text(json.dumps(d), encoding="utf-8")
    run_install(reaper, "en")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["language"] == "en" and d["count_in_bars"] == 1 and d["announce_voice"] == "Amélie"
    kb = (reaper / "reaper-kb.ini").read_text(encoding="utf-8")
    assert '"Custom: ReaCue - Prepare the song"' in kb and kb.count("REACUE_PREPARE") == 1


def test_reaper_running_no_kb_write(reaper, capsys):
    run_install(reaper, running="yes")
    assert not (reaper / "reaper-kb.ini").exists()
    assert "Load ReaScript" in capsys.readouterr().out


def test_missing_reaper_dir(tmp_path, capsys):
    assert S.main(["install", "--lang", "en", "--reaper-dir", str(tmp_path / "nope"), "--mcp", "no",
                   "--reaper-running", "no"]) == 2
    assert "Start REAPER once" in capsys.readouterr().out


def test_claude_desktop_config(tmp_path, monkeypatch):
    cfg = tmp_path / "Claude" / "claude_desktop_config.json"
    cfg.parent.mkdir()
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}), encoding="utf-8")
    monkeypatch.setattr(S, "claude_config_path", lambda *a, **k: cfg)
    reaper = tmp_path / "REAPER"
    (reaper / "Scripts").mkdir(parents=True)
    run_install(reaper, mcp="yes")
    run_install(reaper, mcp="yes")
    d = json.loads(cfg.read_text(encoding="utf-8"))
    assert d["theme"] == "dark" and d["mcpServers"]["other"] == {"command": "x"}
    assert d["mcpServers"]["reacue"]["args"] == [str(ROOT / "run_server.py")]
    assert (cfg.parent / "claude_desktop_config.json.bak-reacue").exists()
    # dossier REAPER non standard : transmis au serveur
    assert d["mcpServers"]["reacue"]["env"]["REAPER_RESOURCE_PATH"] == str(reaper)
    # désinstallation
    assert S.main(["uninstall", "--reaper-dir", str(reaper), "--reaper-running", "no"]) == 0
    d = json.loads(cfg.read_text(encoding="utf-8"))
    assert "reacue" not in d["mcpServers"] and "other" in d["mcpServers"]


def test_claude_bad_json_untouched(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "c.json"
    cfg.write_text("{oops", encoding="utf-8")
    monkeypatch.setattr(S, "claude_config_path", lambda *a, **k: cfg)
    reaper = tmp_path / "REAPER"
    (reaper / "Scripts").mkdir(parents=True)
    run_install(reaper, mcp="yes")
    assert cfg.read_text(encoding="utf-8") == "{oops"
    assert "illisible" in capsys.readouterr().out


def test_uninstall(reaper, monkeypatch, tmp_path):
    monkeypatch.setattr(S, "claude_config_path", lambda *a, **k: tmp_path / "none.json")
    (reaper / "Scripts" / "__startup.lua").write_text("-- autre\n", encoding="utf-8")
    run_install(reaper)
    www = reaper / "reaper_www_root"
    assert (www / "studio.html").exists() and (www / "reacue_studio" / "fonts").is_dir()   # pages copiées
    (www / "prompteur.html").write_text("x")
    (www / "reacue_peaks.json").write_text("{}")
    (www / "reacue_exports").mkdir()
    (www / "reacue_exports" / "a_x.mp3").write_text("x")
    (reaper / "ReaCueMCP" / "last_session.json").write_text("{}")
    assert S.main(["uninstall", "--reaper-dir", str(reaper), "--reaper-running", "no"]) == 0
    assert not (reaper / "Scripts" / "ReaCue").exists()
    assert (reaper / "Scripts" / "__startup.lua").read_text(encoding="utf-8") == "-- autre\n"
    assert "REACUE_" not in (reaper / "reaper-kb.ini").read_text(encoding="utf-8")
    assert (reaper / "ReaCueMCP" / "last_session.json").exists()            # données conservées
    assert not (reaper / "reaper_www_root" / "prompteur.html").exists()
    assert not (www / "studio.html").exists() and not (www / "reacue_studio").exists()
    assert not (www / "reacue_peaks.json").exists() and not (www / "reacue_exports").exists()
    S.main(["uninstall", "--reaper-dir", str(reaper), "--reaper-running", "no", "--purge"])
    assert not (reaper / "ReaCueMCP").exists()


def test_web_port_detection(tmp_path):
    ini = tmp_path / "reaper.ini"
    ini.write_text("[reaper]\ncsurf_cnt=1\ncsurf_0=HTTP 0 8080 '' 'prompteur.html' 0 ''\n", encoding="utf-8")
    assert S.web_ports(ini) == [8080]
    assert S.web_ports(tmp_path / "absent.ini") == []


def test_paths_per_platform(tmp_path):
    home = tmp_path / "home"
    win_env = {"APPDATA": "C:\\Users\\Zoé\\AppData\\Roaming"}
    assert S.reaper_resource_dir("win32", win_env, home) == Path(win_env["APPDATA"]) / "REAPER"
    assert S.reaper_resource_dir("darwin", {}, home) == home / "Library/Application Support/REAPER"
    assert S.reaper_resource_dir("win32", {"REAPER_RESOURCE_PATH": "D:/Portable/REAPER"}, home) == Path("D:/Portable/REAPER")
    assert S.claude_config_path("win32", win_env, home) == Path(win_env["APPDATA"]) / "Claude" / "claude_desktop_config.json"
    assert S.venv_python(Path("C:/R"), "win32") == Path("C:/R") / ".venv" / "Scripts" / "python.exe"
    assert S.venv_python(Path("C:/R"), "win32", windowed=True).name == "pythonw.exe"
    assert S.venv_python(Path("/r"), "darwin") == Path("/r/.venv/bin/python")
    e = S.mcp_entry(Path("C:/R"), "win32")
    assert e["command"].endswith("python.exe") and "env" not in e


def test_reaper_running_detection():
    def fake_win(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, "reaper.exe   1234 Console   1   300 000 K\n", "")

    def fake_mac(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, "", "")
    assert S.reaper_running("win32", run=fake_win) is True
    assert S.reaper_running("darwin", run=fake_mac) is False


def test_stems_action_and_setting(reaper):
    run_install(reaper, "en")
    kb = (reaper / "reaper-kb.ini").read_text(encoding="utf-8")
    assert 'SCR 4 0 REACUE_STEMS "Custom: ReaCue - Separate stems" "ReaCue/ReaCue_Separer_stems.lua"' in kb
    for f in ("ReaCue_stems.lua", "ReaCue_Separer_stems.lua"):
        assert (reaper / "Scripts" / "ReaCue" / f).exists()
    s = json.loads((reaper / "ReaCueMCP" / "reacue_settings.json").read_text(encoding="utf-8"))
    assert s["stems_model"] == "htdemucs"


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_concert_actions_scripts_and_settings(reaper, lang, monkeypatch, tmp_path):
    monkeypatch.setattr(S, "claude_config_path", lambda *a, **k: tmp_path / "none.json")
    run_install(reaper, lang)
    kb = (reaper / "reaper-kb.ini").read_text(encoding="utf-8")
    names = {"fr": ("ReaCue - Concert", "ReaCue - Morceau suivant", "ReaCue - Morceau précédent"),
             "en": ("ReaCue - Concert", "ReaCue - Next song", "ReaCue - Previous song")}[lang]
    for cid, f, n in zip(("REACUE_CONCERT", "REACUE_NEXT_SONG", "REACUE_PREV_SONG"),
                         ("ReaCue_Concert.lua", "ReaCue_Morceau_suivant.lua", "ReaCue_Morceau_precedent.lua"), names):
        assert f'SCR 4 0 {cid} "Custom: {n}" "ReaCue/{f}"' in kb
    for f in ("ReaCue_Concert.lua", "ReaCue_concert_lib.lua", "ReaCue_qrcode.lua", "ReaCue_Morceau_suivant.lua",
              "ReaCue_Morceau_precedent.lua", "ReaCue_run.lua"):
        assert (reaper / "Scripts" / "ReaCue" / f).exists()
    s = json.loads((reaper / "ReaCueMCP" / "reacue_settings.json").read_text(encoding="utf-8"))
    assert s["concert_dir"] is None and s["projects_dir"] is None
    assert "remote_pin" not in json.dumps(s)            # le PIN de la Régie est généré dans REAPER, jamais ici
    S.main(["uninstall", "--reaper-dir", str(reaper), "--lang", lang, "--reaper-running", "no"])
    kb = (reaper / "reaper-kb.ini").read_text(encoding="utf-8")
    assert "REACUE_CONCERT" not in kb and "REACUE_NEXT_SONG" not in kb


def test_uninstall_stems_env(reaper, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(S, "claude_config_path", lambda *a, **k: tmp_path / "none.json")
    inst = tmp_path / "ReaCue"
    (inst / "reaper").mkdir(parents=True)
    for f in S.SCRIPT_FILES:
        (inst / "reaper" / f).write_bytes((ROOT / "reaper" / f).read_bytes())
    sp = S.stems_python(inst)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text("")
    run_install(reaper, install_dir=inst)
    capsys.readouterr()
    S.main(["status", "--reaper-dir", str(reaper)])
    assert json.loads(capsys.readouterr().out)["stems"] is True
    assert S.main(["uninstall", "--reaper-dir", str(reaper), "--reaper-running", "no"]) == 0
    assert (inst / ".venv-demucs").exists() and "conservée" in capsys.readouterr().out
    run_install(reaper, install_dir=inst)
    S.main(["uninstall", "--reaper-dir", str(reaper), "--reaper-running", "no", "--purge"])
    assert not (inst / ".venv-demucs").exists()


def test_stems_paths():
    assert S.stems_python(Path("C:/R"), "win32", windowed=True) == Path("C:/R/.venv-demucs/Scripts/pythonw.exe")
    assert S.stems_python(Path("/r"), "darwin") == Path("/r/.venv-demucs/bin/python")
    assert S.torch_hub_dir({"TORCH_HOME": "/t"}) == Path("/t/hub")
    assert S.torch_hub_dir({}, Path("/h")) == Path("/h/.cache/torch/hub")


def test_all_window_modules_installed():
    """Chaque module chargé par la fenêtre ReaCue (dofile) est copié dans REAPER/Scripts/ReaCue."""
    import re
    import reacue_setup as RS
    root = Path(__file__).resolve().parents[1] / "reaper"
    src = (root / "ReaCue.lua").read_text(encoding="utf-8")
    used = set(re.findall(r'"(ReaCue_[A-Za-z_]+\.lua)"', src)) | {f"ReaCue_tab_{k}.lua" for k in ("song", "concert", "stage", "lighting", "settings")}
    assert used <= set(RS.SCRIPT_FILES), used - set(RS.SCRIPT_FILES)
    for f in RS.SCRIPT_FILES:
        assert (root / f).is_file(), f


def test_antigravity_mcp_config(tmp_path, monkeypatch):
    cfg = tmp_path / ".gemini" / "config" / "mcp_config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"mcpServers": {"existing": {"url": "http://127.0.0.1:8080"}}}), encoding="utf-8")
    monkeypatch.setattr(S, "antigravity_config_path", lambda *a, **k: cfg)
    reaper = tmp_path / "REAPER"
    (reaper / "Scripts").mkdir(parents=True)
    run_install(reaper, mcp="antigravity")
    d = json.loads(cfg.read_text(encoding="utf-8"))
    assert "existing" in d["mcpServers"]
    assert "reacue" in d["mcpServers"]
    assert d["mcpServers"]["reacue"]["args"] == [str(ROOT / "run_server.py")]
    # uninstall
    assert S.main(["uninstall", "--reaper-dir", str(reaper), "--reaper-running", "no"]) == 0
    d = json.loads(cfg.read_text(encoding="utf-8"))
    assert "reacue" not in d["mcpServers"]
    assert "existing" in d["mcpServers"]


def test_cursor_mcp_config(tmp_path, monkeypatch):
    cfg = tmp_path / ".cursor" / "mcp.json"
    cfg.parent.mkdir(parents=True)
    monkeypatch.setattr(S, "cursor_config_path", lambda *a, **k: cfg)
    reaper = tmp_path / "REAPER"
    (reaper / "Scripts").mkdir(parents=True)
    run_install(reaper, mcp="cursor")
    d = json.loads(cfg.read_text(encoding="utf-8"))
    assert "reacue" in d["mcpServers"]
    # uninstall
    assert S.main(["uninstall", "--reaper-dir", str(reaper), "--reaper-running", "no"]) == 0
    d = json.loads(cfg.read_text(encoding="utf-8"))
    assert "reacue" not in d["mcpServers"]


def test_mcp_export_and_multi(tmp_path, monkeypatch):
    reaper = tmp_path / "REAPER"
    (reaper / "Scripts").mkdir(parents=True)
    run_install(reaper, mcp="export")
    exp = reaper / "ReaCueMCP" / "reacue_mcp_config.json"
    assert exp.exists()
    d = json.loads(exp.read_text(encoding="utf-8"))
    assert "reacue" in d["mcpServers"]
    # uninstall removes export file
    assert S.main(["uninstall", "--reaper-dir", str(reaper), "--reaper-running", "no"]) == 0
    assert not exp.exists()


def test_resolve_mcp_targets():
    assert S.resolve_mcp_targets("no", ["claude"]) == []
    assert S.resolve_mcp_targets("0", ["claude"]) == []
    assert S.resolve_mcp_targets("yes", ["claude"]) == ["claude"]
    assert S.resolve_mcp_targets("claude", []) == ["claude"]
    assert S.resolve_mcp_targets("antigravity", []) == ["antigravity"]
    assert S.resolve_mcp_targets("cursor", []) == ["cursor"]
    assert S.resolve_mcp_targets("export", []) == ["export"]
    assert S.resolve_mcp_targets("claude,antigravity", []) == ["antigravity", "claude"]
    assert S.resolve_mcp_targets("all", []) == ["antigravity", "claude", "cursor", "export"]


def test_ask_mcp_selection(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a: "1,2")
    assert S.ask_mcp_selection(["claude", "antigravity"]) == ["antigravity", "claude"]

    monkeypatch.setattr("builtins.input", lambda *a: "0")
    assert S.ask_mcp_selection(["claude"]) == []

    monkeypatch.setattr("builtins.input", lambda *a: "")
    assert S.ask_mcp_selection(["antigravity"]) == ["antigravity"]

    monkeypatch.setattr("builtins.input", lambda *a: "5")
    assert S.ask_mcp_selection([]) == ["export"]
