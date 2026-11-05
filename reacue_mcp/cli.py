"""ReaCue sans Claude : lancé par les boutons « ReaCue - Préparer le morceau » / « ReaCue - Republier
le prompteur » de REAPER (ou à la main).

    <python du venv> -m reacue_mcp.cli prepare      # analyse + régions, click, annonces, prompteur
    <python du venv> -m reacue_mcp.cli publish      # republie seulement le prompteur
    <python du venv> -m reacue_mcp.cli concert --setlist "<Concerts>/Concert.setlist.json"
    <python du venv> -m reacue_mcp.cli concert --name "Concert" --songs "Song A" "Song B"
    <python du venv> -m reacue_mcp.cli timecode     # pistes TIMECODE LTC / MTC seules (onglet Lumière)
    <python du venv> -m reacue_mcp.cli concert-lighting --setlist "<Concerts>/Concert.setlist.json"
                                                    # export grandMA3 du concert déjà construit (onglet Lumière)
    <python du venv> -m reacue_mcp.cli export --job "<ReaCueMCP>/export_job.json"
                                                    # export audio demandé par la page Studio (fenêtre ReaCue)
    <python du venv> -m reacue_mcp.cli export --request '{"stems": ["Basse"], "format": "mp3",
                                                          "range": {"kind": "section", "section": "Refrain 1"}}'
                                                    # même chose à la main (items lus par le pont)
    <python du venv> -m reacue_mcp.cli library      # ReaCue Studio, BIBLIO : reacue_library.json
    <python du venv> -m reacue_mcp.cli notes        # ReaCue Studio, GROUPE : notes de section republiées
    <python du venv> -m reacue_mcp.cli open-song --project "<morceau>.RPP"
                                                    # morceau ouvert depuis BIBLIO : prompteur publié
    (Windows : reacue_cli.py, à la racine, fait la même chose sans dépendre du dossier courant)

Même code que le serveur MCP (mêmes réglages, même mémoire du dernier morceau) : on peut ensuite
continuer avec Claude sans rien perdre. L'avancement est écrit dans
<ressources REAPER>/ReaCueMCP/cli_status.json, lu par le script Lua qui affiche la progression.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path

_JOB = None
_LEASE = None
_LEASE_TOKEN = None


def _dirs():
    from .bridge import BRIDGE_DIR
    return BRIDGE_DIR, BRIDGE_DIR / "cli_status.json", BRIDGE_DIR / "cli.log"


def _status(state: str, **kw):
    _, status, _ = _dirs()
    status.parent.mkdir(parents=True, exist_ok=True)
    d = {"state": state, "time": time.time(), "pid": os.getpid(), **kw}
    from .jobs import atomic_json
    if _JOB is not None:
        # The process may still enrich the concert after publishing its usable result.
        _JOB.update("running", reported_state=state, **kw)
        d.update({k: _JOB.data[k] for k in ("id", "project", "started", "cancel_file", "cancellable", "launch_command")})
    atomic_json(status, d)


def _message(res: dict, title: str) -> str:
    """Résumé lisible pour la fenêtre de REAPER (langue du réglage `language`)."""
    from .i18n import t, is_bpm_from_name_warning, get_lang
    if res.get("error"):
        return t("cli_error", e=res["error"])
    lines = [title, ""]
    if "bpm" in res:
        lines.append(t("cli_tempo", bpm=res["bpm"], sig=res.get("signature", ""), bars=res.get("bars", "?"))
                     + (t("cli_alt", alt=res["alt_bpm"]) if res.get("alt_bpm") else ""))
    secs = res.get("sections") or []
    se = res.get("structure_engine") or {}
    if se.get("message"):
        lines.append(se["message"])
    if secs:
        lines.append("")
        lines.append(t("cli_structure"))
        for s in secs:
            n = s.get("length_bars")
            lines.append(f"  {s.get('bars', ''):>9}  {s['name']}" + (f"  ({n})" if n else ""))
    tcs = res.get("timecode") or {}
    if "enabled" in res and not res.get("error"):          # commande « timecode » (onglet Lumière)
        if not res["enabled"]:
            lines.append(t("tc_tracks_none"))
        for pt in tcs.get("pistes") or []:
            lines.append(t("tc_tracks_line", track=pt.get("piste"), out=pt.get("sortie") or "?",
                           len=round(float(pt.get("longueur_s") or 0)),
                           state=t("tc_tracks_set") if pt.get("generateur_regle") else t("tc_tracks_unset")))
    p = res.get("prompteur") or {}
    if p:
        bits = [t(k) for k, v in (("cli_chords", p.get("chords")), ("cli_drums", p.get("drums"))) if v]
        if p.get("lyrics"):
            bits.append(t("cli_lyrics", n=p["lyrics"]))
        lines.append("")
        sep = ": " if get_lang() == "en" else " : "
        lines.append(t("cli_published") + (sep + ", ".join(bits) if bits else ""))
        g = p.get("grandma3") or {}
        if g.get("cues") and g.get("dossier"):
            lines.append(t("gma3_written", n=g["cues"], d=g["dossier"]))
        if p.get("pdf"):
            lines.append(t("cli_pdf", name=Path(p["pdf"]).name))
        from .lyrics_auto import LAST_INFO as auto_info      # paroles automatiques (Whisper) : créées / échec
        if auto_info.get("message") and not auto_info.get("cached"):
            lines.append("  " + auto_info["message"])
        if p.get("warning"):
            lines.append("  ! " + p["warning"])
    warns = [w for w in res.get("warnings") or [] if not is_bpm_from_name_warning(w)]
    if warns:
        lines.append("")
        lines.extend("! " + w for w in warns[:6])
    return "\n".join(lines)


async def _run(cmd: str, args) -> dict:
    from . import server          # import tardif : librosa est long à charger
    from .i18n import t
    if cmd == "prepare":
        # morceau déjà préparé (mêmes pistes) : on reconstruit en gardant la structure validée
        if not args.reanalyse and await _same_song(server):
            # régions modifiées à la main dans REAPER : reprises comme structure (update_options)
            res = await server.update_options(**_changed_settings(server))
            res["_title"] = t("cli_from_regions") if res.get("structure_from_regions") else t("cli_rebuilt")
            return res
        kw = {}
        if args.bpm:
            kw["bpm_hint"] = args.bpm
        if args.count_in is not None:
            kw["count_in_bars"] = args.count_in
        return await server.prepare_song(**kw)
    if cmd == "publish":
        return await server.set_sections([{"prompteur_seul": True}])
    if cmd == "timecode":
        res = await server.update_timecode_tracks()
        res["_title"] = t("tc_tracks_title")
        return res
    raise ValueError(t("cli_unknown", cmd=cmd))


def _changed_settings(server) -> dict:
    """Réglages à réappliquer au morceau déjà préparé : seulement ceux de reacue_settings.json qui ont
    changé depuis la dernière préparation (les options réglées entre-temps avec Claude sont gardées ;
    session d'une ancienne version, sans instantané des réglages : rien n'est réappliqué)."""
    import inspect
    from .settings import option_defaults
    try:
        before = json.loads(server.SESSION.read_text(encoding="utf-8")).get("settings")
    except (OSError, ValueError):
        return {}
    if not isinstance(before, dict):
        return {}
    allowed = set(inspect.signature(server.update_options).parameters)
    return {k: v for k, v in option_defaults().items()
            if k in allowed and v is not None and before.get(k) != v}


async def _same_song(server) -> bool:
    """Les pistes audio du projet ouvert sont-elles celles du dernier morceau préparé ?"""
    try:
        _, item, _, items = server._load()
    except Exception:
        return False
    return await server._same_song(item, items)


def _concert_message(res) -> str:
    from .i18n import t
    lines = [t("concert_built", name=res.name), ""]
    for d in res.songs:
        lines.append(t("concert_line", n=d["n"], title=d["title"], bpm=d["bpm"], bars=d["bars"]))
    total = res.songs[-1]["stop"] if res.songs else 0
    lines += ["", t("concert_duration", m=int(total // 60), s=int(total % 60)), t("concert_extras_running")]
    g = getattr(res, "lighting", None) or {}
    if g.get("cues") and g.get("dir"):
        lines.append(t("gma3_written", n=g["cues"], d=g["dir"]))
    if res.warnings:
        lines.append("")
        lines.extend("! " + w for w in res.warnings[:6])
    return "\n".join(lines)


def _log_exc(log):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + traceback.format_exc() + "\n")


def _concert(args, log) -> int:
    """Construit (ou reconstruit) un concert, puis enrichit son prompteur (accords, paroles, batterie)."""
    from . import concert as conc
    from .i18n import t
    if args.setlist:
        res = conc.build_from_setlist(args.setlist)
    elif args.name and args.songs:
        res = conc.build_concert(args.name, args.songs, args.gap if args.gap is not None else 4.0)
    else:
        raise ValueError(t("concert_args"))
    _status("done", cmd="concert", message=_concert_message(res), rpp=str(res.rpp))
    try:
        conc.extras_from_setlist(res.setlist)
    except Exception:
        _log_exc(log)
    return 0


def _concert_lighting(args) -> str:
    """Export grandMA3 d'un concert déjà construit, à partir de son prompteur (<nom>.prompteur.json, à côté
    de la setlist) : mêmes fichiers que la construction, réglages lumière actuels ; le bloc « lighting » du
    prompteur est mis à jour (republié s'il est celui affiché par les téléphones)."""
    from types import SimpleNamespace
    from . import concert as conc, lighting
    from .i18n import t
    if not args.setlist:
        raise ValueError(t("concert_args"))
    sl = Path(args.setlist)
    slug = sl.name[:-len(".setlist.json")] if sl.name.endswith(".setlist.json") else sl.stem
    pf = sl.with_name(slug + ".prompteur.json")
    try:
        data = json.loads(pf.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError(t("gma3_concert_missing", f=pf.name)) from None
    name = (data.get("concert") or {}).get("name") or slug
    lines = [t("gma3_concert_title", name=name), ""]
    cfg = lighting.config()
    if not cfg["export"]:
        return "\n".join(lines + [t("gma3_disabled")])
    from .prompter import WWW_DIR
    out = lighting.export_concert(name, data, sl.parent, WWW_DIR, cfg)
    data["lighting"] = lighting.web_data(lighting.show_from_songs(data.get("songs") or [], name), cfg)
    lighting.rehash(data)
    conc.write_prompter(SimpleNamespace(prompter=pf, name=name), data, publish=True, only_if_current=True)
    if out:
        lines.append(t("gma3_written", n=out["cues"], d=out.get("dir")))
    return "\n".join(lines)


def _export(args, log) -> int:
    """Export audio (ReaCue Studio) : l'état est publié dans reaper_www_root/reacue_export.json (lu par la
    page) ; cli_status.json n'est pas touché (la fenêtre ReaCue peut avoir une autre tâche en cours)."""
    from . import export
    from .i18n import t
    if args.job:
        try:
            res = export.run_job_file(args.job)
        except Exception:
            _log_exc(log)
            return 1
        print(json.dumps({k: res[k] for k in ("message", "dir")}, ensure_ascii=False))
        return 0
    if args.request:
        from . import server
        res = asyncio.run(server.export_audio(json.loads(args.request)))
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0 if not res.get("error") else 1
    print(t("cli_export_args"), file=sys.stderr)
    return 2


def _main(argv=None):
    global _JOB, _LEASE, _LEASE_TOKEN
    ap = argparse.ArgumentParser(prog="reacue")
    ap.add_argument("cmd", choices=["prepare", "publish", "concert", "concert-extras", "timecode",
                                    "concert-lighting", "export", "library", "notes", "open-song",
                                    "concert-manage", "import-audio"])
    ap.add_argument("--bpm", type=float, help="tempo approximatif (corrige double/moitié)")
    ap.add_argument("--count-in", type=int, help="mesures de count-in (défaut : réglages, 2)")
    ap.add_argument("--reanalyse", action="store_true",
                    help="refaire l'analyse même si le morceau est déjà préparé (structure remplacée)")
    ap.add_argument("--resource-dir", help="dossier des ressources REAPER (transmis par le script Lua)")
    ap.add_argument("--setlist", help="concert : fichier <nom>.setlist.json")
    ap.add_argument("--name", help="concert : nom du concert")
    ap.add_argument("--songs", nargs="+", help="concert : morceaux dans l'ordre (noms de projets ou chemins .RPP)")
    ap.add_argument("--gap", type=float, help="concert : blanc minimum entre deux morceaux (s)")
    ap.add_argument("--job", help="export : tâche écrite par la fenêtre ReaCue (export_job.json)")
    ap.add_argument("--project", help="open-song : projet .RPP ouvert depuis l'écran BIBLIO de ReaCue Studio")
    ap.add_argument("--request", help="export : demande JSON (stems, format, kbps, range, mode, click)")
    ap.add_argument("--operation", help="management or import operation")
    ap.add_argument("--destination", help="new concert/package destination")
    ap.add_argument("--launch-command", help=argparse.SUPPRESS)
    ap.add_argument("--job-id", help=argparse.SUPPRESS)
    ap.add_argument("--origin-project", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.resource_dir:
        # avant tout import de bridge : BRIDGE_DIR en dépend (REAPER portable, chemin non standard)
        os.environ["REAPER_RESOURCE_PATH"] = str(Path(args.resource_dir))
    from .i18n import t, use_settings_lang, get_lang
    use_settings_lang()
    directory, _, log = _dirs()
    tracked = args.cmd not in ("library", "notes", "open-song")
    if tracked:
        from .jobs import Job, WorkerLease, lease_owned
        _JOB = Job(directory, args.cmd, job_id=args.job_id, project=args.origin_project or "", launch_command=args.launch_command or args.cmd)
        _LEASE = WorkerLease(directory)
        acquired = _LEASE.acquire()
        # MCP spawns extras just before releasing its own build lease. Wait for
        # that handoff instead of running model workers concurrently.
        if args.cmd == "concert-extras" and not acquired:
            deadline = time.monotonic() + 10
            while not acquired and time.monotonic() < deadline:
                time.sleep(0.1)
                acquired = _LEASE.acquire()
        if not acquired:
            _JOB.update("error", message="Un traitement est déjà en cours. Attends sa fin.")
            return 1
        _LEASE_TOKEN = lease_owned.set(True)
        from . import show_lock
        if show_lock.locked(directory):
            _status("error", cmd=args.cmd, message=show_lock.message())
            return 1
    if args.origin_project:
        os.environ["REACUE_EXPECTED_PROJECT"] = args.origin_project
    if args.cmd in ("concert-manage", "import-audio"):
        _status("running", cmd=args.cmd, step=t("cli_running"))
        try:
            progress = lambda text: _status("running", cmd=args.cmd, step=str(text))
            if args.cmd == "concert-manage":
                from .concert_manage import dispatch_request
                data = {"operation": args.operation, "setlist": args.setlist,
                        "name": args.name, "destination": args.destination}
                result = dispatch_request(data, progress=progress)
                field = "concert_manage"
            else:
                from .import_audio import dispatch_request
                data = json.loads(Path(args.job).read_text(encoding="utf-8")) if args.job else json.loads(args.request or "{}")
                if not isinstance(data, dict):
                    raise ValueError("Invalid import request")
                if args.operation:
                    data["operation"] = args.operation
                data["cancel_file"] = _JOB.data["cancel_file"]
                result = dispatch_request(data, progress=progress)
                field = "import_audio"
            _status("done", cmd=args.cmd, message=result.get("message") or ("Terminé." if get_lang() == "fr" else "Done."), **{field: result})
            return 0
        except Exception as e:
            _log_exc(log)
            cancelled = _JOB is not None and _JOB.cancelled
            _status("cancelled" if cancelled else "error", cmd=args.cmd, message=str(e))
            return 130 if cancelled else 1
    if args.cmd == "concert-extras":           # arrière-plan, sans fenêtre de progression
        from . import concert as conc
        try:
            conc.extras_from_setlist(args.setlist)
            return 0
        except Exception:
            _log_exc(log)
            return 1
    if args.cmd == "export":                   # ReaCue Studio : export audio (sans fenêtre de progression)
        return _export(args, log)
    if args.cmd in ("library", "notes", "open-song"):   # ReaCue Studio (BIBLIO, GROUPE) : sans fenêtre de progression
        from . import library
        try:
            if args.cmd == "notes":                    # notes de section enregistrées par la fenêtre ReaCue
                res = library.apply_notes_published()
                library.publish_library()
            elif args.cmd == "open-song":
                if not args.project:
                    print("open-song : --project <morceau>.RPP", file=sys.stderr)
                    return 2
                res = library.publish_project(args.project)
            else:
                d = library.publish_library()
                res = {"songs": len(d["songs"]), "concerts": len(d["concerts"])}
            print(json.dumps(res, ensure_ascii=False))
            return 0
        except Exception:
            _log_exc(log)
            return 1
    if args.cmd == "concert-lighting":         # onglet Lumière : export d'un concert déjà construit
        _status("running", cmd="concert-lighting", step=t("gma3_running"))
        try:
            _status("done", cmd="concert-lighting", message=_concert_lighting(args))
            return 0
        except Exception as e:
            _log_exc(log)
            _status("error", cmd="concert-lighting", message=t("cli_error_log", e=e, log=log))
            return 1
    if args.cmd == "concert":
        _status("running", cmd="concert", step=t("cli_concert_running"))
        try:
            return _concert(args, log)
        except Exception as e:
            _log_exc(log)
            _status("error", cmd="concert", message=t("cli_error_log", e=e, log=log))
            return 1
    titles = {"prepare": t("cli_prepared"), "publish": t("cli_published_title"), "timecode": t("tc_tracks_title")}
    _status("running", cmd=args.cmd, step=t("cli_running"))
    from . import structure
    structure.PROGRESS = lambda msg: _status("running", cmd=args.cmd, step=msg)
    from . import lyrics_auto
    lyrics_auto.PROGRESS = lambda msg: _status("running", cmd=args.cmd, step=msg)
    try:
        res = asyncio.run(_run(args.cmd, args))
        ok = not res.get("error")
        se = res.get("structure_engine") or {}
        extra = {}
        if args.cmd == "prepare":
            # Optional enrichments may warn while the prompter itself is already published.
            # The Lua flow only retries publication when this explicit success is absent.
            extra["prompter_published"] = bool((res.get("prompteur") or {}).get("data"))
            # moteur des sections, lu par la fenêtre (pastille « Structure ») : songformer | reacue | regions
            extra["engine"] = ("regions" if res.get("structure_from_regions") or "structure_engine" not in res
                               else se.get("engine") or "reacue")
            if se.get("fallback"):
                extra["fallback"] = True
            if se.get("missing"):
                extra["structure_missing"] = True
            # débuts de sections douteux (orange dans la fenêtre) : « 9:moved,17:unsure »
            extra["doubts"] = ",".join(f'{d["start_bar"]}:{d["reason"]}' for d in se.get("doubts") or [])
        _status("done" if ok else "error", cmd=args.cmd,
                message=_message(res, res.pop("_title", None) or titles[args.cmd]), **extra)
        return 0 if ok else 1
    except Exception as e:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + traceback.format_exc() + "\n")
        _status("error", cmd=args.cmd, message=t("cli_error_log", e=e, log=log))
        return 1


def main(argv=None):
    global _JOB, _LEASE, _LEASE_TOKEN
    _JOB = None
    _LEASE = None
    _LEASE_TOKEN = None
    before = os.environ.get("REACUE_EXPECTED_PROJECT")
    code = 1
    try:
        code = _main(argv)
        return code
    except Exception as e:
        if _JOB is None:
            raise
        _log_exc(_dirs()[2])
        _status("error", cmd=_JOB.data["cmd"], message=str(e))
        return 1
    finally:
        if _JOB is not None:
            if _JOB.data["cmd"] == "export" and _LEASE and _LEASE.file:
                _status("done" if code == 0 else "error", cmd="export", message=_JOB.data.get("message", ""))
            _JOB.update("done" if code == 0 else "cancelled" if code == 130 else "error")
        _JOB = None
        if _LEASE is not None:
            _LEASE.release()
        _LEASE = None
        if _LEASE_TOKEN is not None:
            from .jobs import lease_owned
            lease_owned.reset(_LEASE_TOKEN)
        _LEASE_TOKEN = None
        if before is None:
            os.environ.pop("REACUE_EXPECTED_PROJECT", None)
        else:
            os.environ["REACUE_EXPECTED_PROJECT"] = before


if __name__ == "__main__":
    sys.exit(main())
