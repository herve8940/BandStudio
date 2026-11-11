"""Mentions légales : THIRD_PARTY_NOTICES, CITATION, README/LISEZMOI, accord « J'accepte » des installateurs
de l'analyse de structure (refus, acceptation tapée, variable d'environnement, mémorisation), réglages Lua.
Legal notices, licence acceptance in the structure installers, settings tab."""
import os
try:
    import pty
except ImportError:
    pty = None
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- documents
def test_third_party_notices_content():
    txt = " ".join((ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8").split())
    for needle in ("SongFormer", "CC BY 4.0", "MuQ", "CC BY-NC 4.0", "MusicFM", "pretrained_msd.pt",
                   "Demucs", "luaqrcode", "PyTorch" if "PyTorch" in txt else "torch", "easydict", "LGPL-3.0",
                   "REAPER", "Cockos", "Anthropic", "arXiv:2510.02797", "22 octobre 2026"):
        assert needle in txt, needle
    assert re.search(r"[Ii]ncertaine|uncertain", txt)
    assert "non commercial" in txt.lower() and "non-commercial" in txt.lower()
    assert "pas un avis juridique" in txt and "not legal advice" in txt


def test_citation_cff_valid():
    d = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    assert d["cff-version"] == "1.2.0" and d["license"] == "MIT"
    titles = " ".join(r["title"] for r in d["references"])
    for t in ("SongFormer", "MuQ", "Foundation Model for Music Informatics", "Hybrid Transformers"):
        assert t in titles
    init = (ROOT / "desktop/studio/diagnostics.py").read_text(encoding="utf-8")
    ver = re.search(r"VERSION\s*=\s*['\"]([^'\"]+)['\"]", init).group(1)
    assert d["version"].replace("-beta", "b1") == ver


@pytest.mark.parametrize("doc,anchor,words", [
    ("README_REACUE.md", "#licences-responsibilities-and-disclaimers",
     ("as is", "non-commercial", "CC BY-NC 4.0", "not affiliated", "not legal advice", "no audio and no lyrics")),
    ("LISEZMOI.md", "#licences-responsabilités-et-avertissements",
     ("tel quel", "non commercial", "CC BY-NC 4.0", "ni affilié", "pas un avis juridique", "ni audio ni paroles")),
])
def test_readme_disclaimer_section(doc, anchor, words):
    txt = (ROOT / doc).read_text(encoding="utf-8")
    head = txt[:3000]
    assert anchor in head and "THIRD_PARTY_NOTICES.md" in head        # lien depuis le haut du document
    flat = " ".join(txt.replace("**", "").split())
    for w in words:
        assert w in flat, (doc, w)
    assert "ni IA ni internet" not in txt and "no AI and no internet" not in txt


def _slug(title):
    s = title.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s)
    return "#" + s.replace(" ", "-")


@pytest.mark.parametrize("doc", ["README.md", "LISEZMOI.md", "THIRD_PARTY_NOTICES.md",
                                 "docs/TUTORIEL_fr.md", "docs/TUTORIAL_en.md"])
def test_internal_links(doc):
    p = ROOT / doc
    txt = p.read_text(encoding="utf-8")
    anchors = {_slug(m.group(1)) for m in re.finditer(r"^#+\s+(.+)$", txt, re.M)}
    for target in re.findall(r"\]\(([^)\s]+)\)", txt):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if target.startswith("#"):
            assert target in anchors, (doc, target)
            continue
        path = target.split("#")[0]
        assert (p.parent / path).exists(), (doc, target)


def test_no_model_weights_tracked():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    bad = [f for f in files if re.search(r"\.(safetensors|pt|pth|ckpt|onnx|th)$", f)]
    assert not bad
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pat in (".venv-structure/", "/structure/", "*.safetensors", "*.pt", "ckpts/"):
        assert pat in gi


# --------------------------------------------------------------------------- installateur macOS (bash)
def _mac_sandbox(tmp_path):
    """Copie minimale de ReaCue + faux uname (Darwin), faux uv, faux curl qui note ses appels et échoue."""
    inst = tmp_path / "ReaCue"
    (inst / "install").mkdir(parents=True)
    shutil.copy(ROOT / "install" / "install_structure_mac.sh", inst / "install")
    shutil.copy(ROOT / "requirements-structure.txt", inst)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    calls = tmp_path / "calls.txt"
    for name, body in (("uname", 'if [ "$1" = -m ]; then echo x86_64; else echo Darwin; fi'),
                       ("uv", f'echo uv "$@" >> "{calls}"; exit 1'),
                       ("curl", f'echo curl "$@" >> "{calls}"; exit 22'),
                       ("git", "exit 1")):
        f = bin_ / name
        f.write_text("#!/bin/bash\n" + body + "\n")
        f.chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_}:/usr/bin:/bin", HOME=str(tmp_path))
    env.pop("REACUE_STRUCTURE_ACCEPT", None)
    return inst, env, calls


def _run_mac(inst, env, lang="fr", stdin=subprocess.DEVNULL):
    if shutil.which("bash") is None:
        pytest.skip("bash non disponible sur ce système")
    return subprocess.run(["bash", str(inst / "install" / "install_structure_mac.sh"), lang], env=env,
                          stdin=stdin, capture_output=True, text=True, timeout=60)


def _run_mac_tty(inst, env, typed, lang="fr"):
    """Lance l'installateur dans un vrai terminal (pty) et tape `typed` + Entrée."""
    if pty is None:
        pytest.skip("pty non disponible sur Windows")
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe("bash", ["bash", str(inst / "install" / "install_structure_mac.sh"), lang], env)
    out = b""
    sent = False
    while True:
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
        if not sent and b"tape exactement" in out or not sent and b"type exactly" in out:
            os.write(fd, typed.encode("utf-8") + b"\r")
            sent = True
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status), out.decode("utf-8", "replace")


def test_mac_refuses_without_acceptance(tmp_path):
    inst, env, calls = _mac_sandbox(tmp_path)
    r = _run_mac(inst, env)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "CC BY-NC 4.0" in r.stdout and "NON COMMERCIAL" in r.stdout and "THIRD_PARTY_NOTICES.md" in r.stdout
    assert "rien n'a été installé" in r.stdout
    assert not calls.exists()                                   # aucun téléchargement
    assert not (inst / "structure" / ".licenses_accepted").exists()


def test_mac_env_acceptance_then_downloads(tmp_path):
    inst, env, calls = _mac_sandbox(tmp_path)
    env["REACUE_STRUCTURE_ACCEPT"] = "yes"
    r = _run_mac(inst, env, lang="en")
    marker = inst / "structure" / ".licenses_accepted"
    assert marker.exists() and marker.read_text().splitlines()[0].startswith("songformer-ccby4+muq-weights-ccbync4")
    assert "Licences accepted" in r.stdout
    assert calls.exists() and "curl" in calls.read_text()        # téléchargement seulement après l'accord
    assert r.returncode == 1                                     # faux curl : échec attendu, après l'accord


def test_mac_typed_acceptance_and_memory(tmp_path):
    inst, env, calls = _mac_sandbox(tmp_path)
    code, out = _run_mac_tty(inst, env, "j'accepte")             # mauvaise casse : refus
    assert code == 3 and not calls.exists(), out
    code, out = _run_mac_tty(inst, env, "J’accepte")             # apostrophe typographique : accepté
    assert (inst / "structure" / ".licenses_accepted").exists(), out
    assert calls.exists()
    # mémorisé : plus de question, même sans terminal ni variable d'environnement
    calls.unlink()
    r = _run_mac(inst, env)
    assert "tape exactement" not in r.stdout and calls.exists()


def test_mac_english_prompt(tmp_path):
    inst, env, calls = _mac_sandbox(tmp_path)
    code, out = _run_mac_tty(inst, env, "I accept", lang="en")
    assert "NON-COMMERCIAL USE ONLY" in out and "I accept" in out
    assert (inst / "structure" / ".licenses_accepted").exists()


def test_stems_installers_licence_info():
    for f in ("install/install_stems_mac.sh", "install/install_stems_windows.ps1"):
        txt = (ROOT / f).read_text(encoding="utf-8-sig")
        assert "MIT" in txt and "THIRD_PARTY_NOTICES.md" in txt and "J'accepte" not in txt
    ps = (ROOT / "install" / "install_stems_windows.ps1").read_bytes()
    assert ps.startswith(b"\xef\xbb\xbf") and b"\r\n" in ps and b"\n" not in ps.replace(b"\r\n", b"")


# --------------------------------------------------------------------------- installateur Windows (PowerShell)
PWSH = shutil.which("pwsh")


def _win_sandbox(tmp_path):
    inst = tmp_path / "ReaCue"
    (inst / "install").mkdir(parents=True)
    shutil.copy(ROOT / "install" / "install_structure_windows.ps1", inst / "install")
    shutil.copy(ROOT / "requirements-structure.txt", inst)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    uv = bin_ / "uv"
    uv.write_text("#!/bin/bash\nexit 1\n")
    uv.chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_}:/usr/bin:/bin:{os.path.dirname(PWSH)}", USERPROFILE=str(tmp_path),
               TEMP=str(tmp_path))
    env.pop("REACUE_STRUCTURE_ACCEPT", None)
    return inst, env


@pytest.mark.skipif(not PWSH, reason="pwsh absent")
def test_windows_refuses_then_env_accepts(tmp_path):
    inst, env = _win_sandbox(tmp_path)
    ps1 = str(inst / "install" / "install_structure_windows.ps1")
    r = subprocess.run([PWSH, "-NoProfile", "-File", ps1, "-Lang", "fr"], env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "CC BY-NC 4.0" in r.stdout and "rien n'a été installé" in r.stdout
    assert not (inst / "structure" / ".licenses_accepted").exists()
    env["REACUE_STRUCTURE_ACCEPT"] = "yes"
    r = subprocess.run([PWSH, "-NoProfile", "-File", ps1, "-Lang", "en"], env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=120)
    marker = inst / "structure" / ".licenses_accepted"
    assert marker.exists(), r.stdout + r.stderr
    assert marker.read_text(encoding="utf-8-sig").splitlines()[0].startswith("songformer-ccby4")
    assert "Licences accepted" in r.stdout
    assert r.returncode != 3


# --------------------------------------------------------------------------- fenêtre ReaCue, onglet Réglages
def test_settings_tab_licences_and_noncommercial():
    lua = (ROOT / "reaper" / "ReaCue_tab_settings.lua").read_text(encoding="utf-8")
    assert "open_licences" in lua and "THIRD_PARTY_NOTICES.md" in lua
    assert "Usage non commercial uniquement" in lua and "Non-commercial use only" in lua
    assert "https://github.com/herve8940/BandStudio/blob/main/THIRD_PARTY_NOTICES.md" in lua


def test_settings_tab_licences_runs(tmp_path):
    lupa = pytest.importorskip("lupa")
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    install = tmp_path / "inst"
    install.mkdir()
    (install / "THIRD_PARTY_NOTICES.md").write_text("x")
    src = (ROOT / "reaper" / "ReaCue_tab_settings.lua").read_text(encoding="utf-8")
    lua.execute("""
      opened = {}
      os = os or {}
      os.execute = function(c) table.insert(opened, c) return true end
      reaper = { GetOS = function() return "OSX64" end, ExecProcess = function(c) table.insert(opened, c) return "" end }
    """)
    make = lua.execute("return function(src) return load(src)() end")(src)
    ctx = lua.eval("""function(dir)
      local L = { exists = function(p) local f = io.open(p, 'rb'); if f then f:close() return true end return false end }
      local R = { install_dir = function() return dir end, is_windows = function() return false end,
                  shq = function(s) return "'" .. s .. "'" end, winq = function(s) return '"' .. s .. '"' end }
      return { L = L, U = {}, T = {}, R = R, SEP = '/', dir = dir, tr = function(t, k) return t.fr[k] end }
    end""")(str(install))
    M = make(ctx)
    target = M.open_licences()
    assert Path(target) == install / "THIRD_PARTY_NOTICES.md"
    assert "open '" in lua.eval("opened[1]")
    (install / "THIRD_PARTY_NOTICES.md").unlink()
    assert M.licences_target() == "https://github.com/herve8940/BandStudio/blob/main/THIRD_PARTY_NOTICES.md"
