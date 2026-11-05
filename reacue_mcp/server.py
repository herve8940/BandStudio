"""Serveur MCP ReaCue : prépare automatiquement un morceau dans REAPER."""
from __future__ import annotations

from .jobs import managed_job

import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

from .analysis import analyze, analyze_stems, resection, reference_index, assign_roles, Analysis
from .bridge import Bridge, BridgeError, BRIDGE_DIR
from .i18n import t, use_settings_lang, localize_analysis, get_lang
from .planner import Options, build_plan
from .settings import option_defaults
from .voice import Voice
from . import prompter
from . import chords
from . import lyrics
from . import drums
from . import sheet
from . import structure
from . import timecode
from . import studio
from .regions import regions_to_sections, same_structure

mcp = FastMCP(
    "reacue",
    instructions=(
        "Pilote REAPER pour préparer un morceau pour le live : à partir d'un MP3/WAV, détecte "
        "tempo, mesures et sections, puis crée la carte de tempo, les régions, les marqueurs de cue, "
        "une piste CUES et une piste CLICK. Outil principal : prepare_song. Après coup, utilise "
        "set_sections pour corriger les noms/limites si l'utilisateur le demande. Les numéros de mesure "
        "côté outils commencent à 1 (1re mesure du morceau, après le count-in). Les régions que "
        "l'utilisateur a modifiées à la main dans REAPER sont reprises automatiquement par prepare_song "
        "(morceau déjà préparé), update_options et rename_section ; set_sections et set_grid imposent "
        "la structure donnée et remplacent ces régions."
    ),
)
bridge = Bridge()
SESSION = BRIDGE_DIR / "last_session.json"


GENERATED_TRACKS = ("CLICK", "CUES", "VOIX", "VOICE") + timecode.TRACKS


def _new_options(**kw) -> Options:
    """Options initiales : reacue_settings.json, puis les paramètres explicitement donnés."""
    d = option_defaults()
    d.update({k: v for k, v in kw.items() if v is not None})
    return Options(**{k: v for k, v in d.items() if k in Options.__dataclass_fields__})


def _save(analysis: Analysis, item: dict, opts: Options, items: list[dict] | None = None):
    """items : positions ORIGINALES de tous les stems (jamais celles déjà déplacées par un apply)."""
    SESSION.parent.mkdir(parents=True, exist_ok=True)
    d = {"analysis": analysis.to_dict(), "item": item, "options": asdict(opts),
         # réglages du fichier au moment de la préparation : la CLI n'en réapplique que les changements
         "settings": option_defaults()}
    if items:
        d["items"] = items
    SESSION.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _load():
    if not SESSION.exists():
        raise BridgeError(t("no_session"))
    d = json.loads(SESSION.read_text(encoding="utf-8"))
    # options d'une autre version : clés inconnues ignorées, clés absentes = valeurs par défaut
    opts = Options(**{k: v for k, v in (d.get("options") or {}).items() if k in Options.__dataclass_fields__})
    return Analysis.from_dict(d["analysis"]), d["item"], opts, d.get("items")


def _bridge_version(info: dict) -> tuple:
    try:
        return tuple(int(x) for x in str(info.get("bridge", "0")).split(".")[:2])
    except ValueError:
        return (0, 0)


def _common_title(files: list[str]) -> str:
    stems = [Path(f).stem for f in files]
    pre = os.path.commonprefix(stems).rstrip(" -_.")
    return pre if len(pre) >= 3 else stems[0]


async def _apply(analysis: Analysis, item: dict, opts: Options, items: list[dict] | None = None) -> dict:
    from . import show_lock
    if show_lock.locked():
        return {"error": show_lock.message()}
    render, render_count, vwarn = None, None, []
    info = None
    if items or opts.voice_cues or opts.voice_count_in:
        info = await bridge.call("ping")
    if items and _bridge_version(info) < (1, 2):
        raise BridgeError(t("old_bridge_stems"))
    if opts.voice_cues or opts.voice_count_in:
        if _bridge_version(info) < (1, 1):
            vwarn.append(t("old_bridge_voice"))
        else:
            v = await asyncio.to_thread(Voice, BRIDGE_DIR / "voice", opts.voice_name, 200, get_lang())
            vc = await asyncio.to_thread(Voice, BRIDGE_DIR / "voice", opts.count_voice,
                                         opts.count_rate, opts.count_lang)
            if v.available:
                render, render_count = v.render, vc.render
            vwarn = v.warnings + [w for w in vc.warnings if w not in v.warnings]
    # piste des appels vocaux : VOICE en anglais (pont ≥ 1.3, qui la reconnaît comme piste générée)
    vtrack = "VOICE" if get_lang() == "en" and info and _bridge_version(info) >= (1, 3) else "VOIX"
    plan, summary = await asyncio.to_thread(build_plan, analysis, item, opts, render, render_count, items,
                                            vtrack)
    timeline = plan.pop("prompter", None)
    # pistes timecode pour la console lumière (réglages gma3_ltc_output / gma3_mtc_output)
    tc_cfg = timecode.config()
    tc_warn = []
    if tc_cfg["enabled"] and info is None:
        info = await bridge.call("ping")
    if info is not None and _bridge_version(info) >= (1, 4):
        plan["timecode"] = timecode.plan_block(tc_cfg, summary["song_end_s"] + timecode.TAIL_S)
    elif tc_cfg["enabled"]:
        tc_warn.append(t("tc_old_bridge"))
    await _check_items(plan, info)
    res = await bridge.call("apply_plan", plan, timeout=60)
    if res.get("timecode"):
        tc_sum, w = timecode.handle_result(res["timecode"], tc_cfg)
        if tc_sum:
            summary["timecode"] = tc_sum
        tc_warn += w
    _save(analysis, item, opts, items)
    if timeline:
        if info is None:
            try:
                info = await bridge.call("ping")
            except Exception:
                info = None
        try:
            summary["prompteur"] = await asyncio.to_thread(_publish_prompter, analysis, item, timeline, items,
                                                           _project_of(info), plan.get("items"), plan.get("item"))
        except Exception as e:          # le prompteur ne doit jamais bloquer la préparation
            summary.setdefault("warnings", []).append(t("prompter_not_updated", e=e))
    if analysis.stems:
        summary["stem_roles"] = analysis.stems
    summary["warnings"] += vwarn + res.get("warnings", []) + tc_warn
    summary["reaper"] = {"regions": len(res["state"]["regions"]), "markers": len(res["state"]["markers"]),
                         "tempo_markers": len(res["state"]["tempo"]),
                         "click_items": res.get("click_items"), "cue_items": res.get("cue_items"),
                         "voice_items": res.get("voice_items")}
    return summary


async def _check_items(plan: dict, info: dict | None):
    """Vérifie AVANT tout effacement que les items à caler existent dans le projet ouvert."""
    want = [m["guid"] for m in plan.get("items") or []] + ([plan["item"]["guid"]] if plan.get("item") else [])
    if not want:
        return
    if info is None:
        info = await bridge.call("ping")
    if _bridge_version(info) < (1, 2):
        return
    found = {d.get("guid") for d in (await bridge.call("get_audio_items")).get("items") or []}
    if any(g not in found for g in want):
        raise BridgeError(t("wrong_project"))


async def _same_song(item: dict, items: list[dict] | None) -> bool:
    """Les items audio du projet ouvert sont-ils ceux du dernier morceau préparé (GUID + fichier) ?"""
    try:
        found = (await bridge.call("get_audio_items")).get("items") or []
    except Exception:
        return False
    want = items or [item]
    key = lambda L: sorted((d.get("guid"), d.get("file")) for d in L)
    return bool(found) and key(found) == key(want)


async def _from_regions(a: Analysis, item: dict, opts: Options, items: list[dict] | None,
                        adopt: bool = True) -> tuple[Analysis, bool, list[str]]:
    """Structure lue dans les régions du projet REAPER, si elles ont été modifiées à la main.

    Seulement pour le MÊME morceau (mêmes items) : un autre projet ou un projet consolidé n'est jamais
    lu (il sera refusé ensuite par _check_items, rien n'est modifié). Renvoie (analyse, changé ?,
    avertissements). adopt=False : détecte seulement (l'analyse renvoyée est inchangée)."""
    if not await _same_song(item, items):
        return a, False, []
    try:
        regions = (await bridge.call("get_state")).get("regions")
    except Exception:
        return a, False, []
    if regions is None:
        return a, False, []
    plan, _ = await asyncio.to_thread(build_plan, a, item, opts, None, None, items)
    timeline = plan["prompter"]
    ignore = (plan["regions"][0]["name"],) if opts.song_region and plan["regions"] else ()
    secs, warns = regions_to_sections(regions, timeline["bar_times"], timeline["count_in_bars"], a.n_bars,
                                      a.sections, ignore)
    if not secs:
        return a, False, [t("regions_none")] if regions else []
    if same_structure(secs, a.sections):
        return a, False, []
    if not adopt:
        return a, True, warns
    return resection(a, secs), True, warns


async def _apply_from_regions(a, item, opts, items) -> dict:
    """Reprend les régions modifiées à la main (si besoin), puis reconstruit tout."""
    a, changed, warns = await _from_regions(a, item, opts, items)
    res = await _apply(a, item, opts, items)
    if changed:
        res["structure_from_regions"] = True
    res["warnings"] = warns + res.get("warnings", [])
    return res


async def _publish_only(analysis, item, opts, items) -> dict:
    """Met à jour le prompteur des musiciens (paroles, accords…) sans rien changer dans REAPER."""
    plan, summary = await asyncio.to_thread(build_plan, analysis, item, opts, None, None, items)
    timeline = plan.pop("prompter")
    try:
        project = _project_of(await bridge.call("ping"))
    except Exception:
        project = None
    out = await asyncio.to_thread(_publish_prompter, analysis, item, timeline, items, project,
                                  plan.get("items"), plan.get("item"))
    return {"prompteur": out, "reaper": t("unchanged"), "warnings": [],
            "sections": [{"name": s.name, "bars": f"{s.start_bar + 1}-{s.end_bar}"} for s in analysis.sections]}


@managed_job
async def export_audio(request: dict) -> dict:
    """Export audio des stems du projet ouvert (items lus par le pont) ; voir export.py."""
    from . import show_lock
    if show_lock.locked():
        return {"error": show_lock.message()}
    from . import export
    info = await bridge.call("ping")
    found = (await bridge.call("get_audio_items")).get("items") or []
    song = None
    try:
        song = json.loads((prompter.WWW_DIR / prompter.SONG_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    job = export.mcp_job(request, found, _project_of(info), song=song)
    try:
        res = await asyncio.to_thread(export.run_job, job)
    except export.ExportError as e:
        return {"error": str(e)}
    return {"export": res, "warnings": []}


@managed_job
async def update_timecode_tracks() -> dict:
    """Pistes TIMECODE LTC / MTC seules (bouton de l'onglet Lumière de la fenêtre ReaCue, CLI « timecode ») :
    même plan et même suivi que la préparation (timecode.plan_block / handle_result), sans toucher au reste
    du projet. Réglages vides : les pistes timecode existantes sont retirées. Pont ≥ 1.5."""
    from . import show_lock
    if show_lock.locked():
        return {"error": show_lock.message()}
    use_settings_lang()
    cfg = timecode.config()
    info = await bridge.call("ping")
    if _bridge_version(info) < (1, 5):
        return {"error": t("tc_old_bridge")}
    block = timecode.plan_block(cfg, 0.0)
    block["tail"] = timecode.TAIL_S
    res = await bridge.call("timecode_tracks", block, timeout=60)
    tc = (res or {}).get("timecode") or {}
    summ, warns = timecode.handle_result(tc, cfg)
    return {"enabled": cfg["enabled"], "timecode": summ, "length_s": tc.get("length"),
            "warnings": warns}


def _project_of(info: dict | None) -> str | None:
    """Chemin du .RPP ouvert dans REAPER (réponse de « ping ») ; None si le projet n'est pas enregistré."""
    p = (info or {}).get("project") or ""
    return p if str(p).lower().endswith(".rpp") else None


def _export_lighting(song: dict, project: str | None) -> tuple[dict | None, str | None]:
    """Export grandMA3 du morceau : (résultat, avertissement). Jamais bloquant."""
    from . import lighting
    try:
        res = lighting.export_song(song, project)
    except Exception as e:
        return None, t("gma3_failed", e=e)
    return res, None


def _publish_prompter(analysis, item, timeline, items, project: str | None = None,
                      plan_items: list[dict] | None = None, plan_item: dict | None = None):
    from . import chord_model
    chord_model.LAST.clear()
    act = prompter.stem_activity(analysis, items)
    grid, chord_warn = None, None
    names = [d["file"] for d in items] if items else [item.get("file", "")]
    try:                                # les accords ne doivent jamais bloquer le prompteur
        grid = chords.cached_chords(analysis, items, prompter.key_from_names(names))
        chord_warn = chord_model.LAST.get("warning")
        if not chord_warn and (chord_model.LAST.get("fallback") or chord_model.LAST.get("error")):
            chord_warn = chord_model.LAST.get("message")
    except Exception as e:
        chord_warn = t("chords_failed", e=e)
    from . import lyrics_auto, words as word_alignment
    lyrics_auto.LAST_INFO.clear()
    word_alignment.LAST_INFO.clear()
    lyric_lines, lyr_warn = None, None
    try:                                # les paroles non plus
        lyric_lines = lyrics.cached_lyrics(analysis, items)
    except Exception as e:
        lyr_warn = t("lyrics_failed", e=e)
    kit, drum_warn = None, None
    try:                                # la batterie non plus
        if any(r == "drums" for r in assign_roles([d["file"] for d in items or []])) or "drums" in (analysis.stems or {}):
            kit = drums.cached_drums(analysis, items)
            drum_warn = (kit or {}).get("warning")
    except Exception as e:
        drum_warn = t("drums_failed", e=e)
    song = prompter.build_song(analysis, item, timeline, items, act, chords=grid, lyrics=lyric_lines, drums=kit)
    from . import library
    library.attach(song, project)        # projet + notes de section (écran GROUPE de ReaCue Studio)
    light, light_warn = _export_lighting(song, project)     # lumière grandMA3 (onglet Lumière du prompteur)
    library.record_song(song, project)   # résumé pour l'écran BIBLIO
    out = prompter.publish(song)
    peaks_warn = None
    try:                                # formes d'onde de ReaCue Studio (jamais bloquantes)
        placed = studio.placed_items(items, item, plan_items, plan_item)
        if placed:
            out["studio"] = studio.publish_peaks(placed, song)
    except Exception as e:
        peaks_warn = t("studio_peaks_failed", e=e)
    out["chords"] = bool(song.get("chords"))
    out["lyrics"] = len(song.get("lyrics") or [])
    auto_info = dict(lyrics_auto.LAST_INFO)
    out["lyrics_auto"] = auto_info
    auto_warn = auto_info.get("warning")
    if not auto_warn and (auto_info.get("error") or auto_info.get("missing")):
        auto_warn = auto_info.get("message")
    if lyric_lines:
        alignment = dict(word_alignment.LAST_INFO)
        out["lyrics_alignment"] = alignment
        if alignment.get("error"):
            lyr_warn = alignment.get("message") or t("words_failed", e=alignment["error"])
        elif alignment.get("missing"):
            lyr_warn = t("words_unavailable")
        elif alignment.get("total") and alignment.get("lines", 0) < alignment["total"]:
            lyr_warn = t("words_partial", n=alignment.get("lines", 0), total=alignment["total"])

    out["drums"] = bool(song.get("drums"))
    if light:
        out["grandma3"] = {"cues": light["cues"], "dossier": light.get("dir")}
    pdf_warn = None
    try:                                # grille PDF dans le dossier du morceau (jamais bloquante)
        folder = sheet.song_folder(names)
        if folder is not None:
            out["pdf"] = str(sheet.write_sheet(song, folder))
    except Exception as e:
        pdf_warn = t("sheet_failed", e=e)
    warns = [w for w in (chord_warn, lyr_warn, auto_warn, drum_warn, light_warn, pdf_warn, peaks_warn) if w]
    if warns:
        out["warning"] = " ; ".join(warns)
    out["url"] = t("prompter_url", page=prompter.PAGE_NAME)
    out["instruments"] = song["roles"]
    return out


@mcp.tool()
async def reaper_status() -> dict:
    """Vérifie que REAPER et le script ReaCue_Bridge.lua répondent."""
    use_settings_lang()
    ok, why = bridge.alive()
    if not ok:
        return {"connected": False, "reason": why, "bridge_dir": str(BRIDGE_DIR)}
    return {"connected": True, **(await bridge.call("ping"))}


@mcp.tool()
@managed_job
async def prepare_song(
    file_path: str | None = None,
    count_in_bars: int | None = None,
    tempo_mode: Literal["auto", "constant", "beatmap"] | None = None,
    beats_per_bar: int | None = None,
    bpm_hint: float | None = None,
    click: bool = True,
    click_to_master: bool | None = None,
    click_hw_output: int | None = None,
    cue_lead_bars: int | None = None,
    song_region: bool = False,
    voice_cues: bool | None = None,
    voice_count_in: bool | None = None,
    voice_count_each: bool | None = None,
    voice_name: str | None = None,
    reanalyse: bool = False,
) -> dict:
    """Prépare tout automatiquement dans REAPER pour le morceau importé.

    Utilise l'item audio sélectionné (sinon le premier du projet). Si file_path est donné,
    le fichier est d'abord importé sur une piste AUDIO.
    Étapes : analyse (BPM, mesures, sections) → calage de l'audio sur la grille → carte de tempo
    → régions colorées par section → marqueurs « → Section » N mesures avant → piste CUES → piste CLICK
    avec count-in → piste VOIX : appels vocaux (« Refrain », « Pont »…) cue_lead_bars mesure(s) avant
    chaque section et décompte sur le count-in (voix du système : macOS `say`, Windows SAPI ;
    voice_name pour choisir : Thomas, Amélie, Microsoft Hortense Desktop…). Remplace les marqueurs/régions/tempo et pistes CLICK/CUES existants.

    tempo_mode : "constant" (un seul tempo), "beatmap" (la grille suit le morceau mesure par mesure,
    pour un enregistrement joué sans click), "auto" choisit selon la stabilité.
    beats_per_bar : forcer 3 ou 4 si la détection se trompe. bpm_hint : tempo approximatif connu
    (corrige les erreurs de double/moitié). click_hw_output : sortie physique du click
    (0 = sorties 1/2, 2 = 3/4…), avec click_to_master=False pour qu'il n'aille pas en façade.
    Les paramètres non donnés prennent les valeurs de reacue_settings.json (count-in 2, annonce sur
    l'avant-dernière mesure, décompte anglais, langue des régions et annonces…).
    Morceau déjà préparé dont l'utilisateur a modifié les régions à la main dans REAPER (déplacées,
    renommées, ajoutées, supprimées) : ces régions deviennent la structure, sans réanalyse
    (résultat : structure_from_regions). reanalyse=True, bpm_hint ou beats_per_bar : analyse complète.
    """
    from . import show_lock
    if show_lock.locked():
        return {"error": show_lock.message()}
    use_settings_lang()
    if not (file_path or reanalyse or bpm_hint or beats_per_bar):
        try:
            a, item0, opts0, items0 = _load()
        except Exception:
            a = None
        if a is not None:
            a, changed, warns = await _from_regions(a, item0, opts0, items0)
            if changed:
                given = dict(count_in_bars=count_in_bars, tempo_mode=tempo_mode, click_to_master=click_to_master,
                             click_hw_output=click_hw_output, cue_lead_bars=cue_lead_bars,
                             voice_cues=voice_cues, voice_count_in=voice_count_in,
                             voice_count_each=voice_count_each, voice_name=voice_name)
                for k, v in given.items():
                    if v is not None:
                        setattr(opts0, k, v)
                res = await _apply(a, item0, opts0, items0)
                res["structure_from_regions"] = True
                res["warnings"] = warns + res.get("warnings", [])
                return res
    items = None
    if file_path:
        p = Path(file_path).expanduser()
        if not p.exists():
            return {"error": t("file_not_found", path=p)}
        item = await bridge.call("import_file", {"file": str(p), "track_name": "AUDIO"})
    else:
        info = await bridge.call("ping")
        if _bridge_version(info) < (1, 2):
            # pont 1.1 : pas de get_audio_items ; plusieurs pistes "musique" = stems probables
            tracks = (await bridge.call("get_state"))["tracks"]
            if len([tr for tr in tracks if tr not in GENERATED_TRACKS]) > 1:
                return {"error": t("old_bridge_stems")}
            item = await bridge.call("get_audio_item")
        else:
            res = await bridge.call("get_audio_items")
            # plusieurs items = stems : on les prend TOUS, quelle que soit la sélection,
            # pour qu'ils restent synchronisés (déplacés du même décalage)
            found = res.get("items") or []
            if not found:
                return {"error": t("no_audio_item")}
            if len(found) == 1:
                item = found[0]
            else:
                items = found
    stem_warn = []
    if items:
        files = [d["file"] for d in items]
        ref = items[reference_index(files)]
        item = ref
        def t0(d):      # position sur la timeline du t=0 du fichier source
            return d["position"] - d.get("offset", 0.0) / (d.get("rate") or 1.0)
        stems = [{"file": d["file"], "shift": t0(d) - t0(ref)} for d in items]
        rates = {round(d.get("rate") or 1.0, 4) for d in items}
        if len(rates) > 1:
            stem_warn.append(t("stem_rates"))
        item["title"] = _common_title(files)
        analysis = await asyncio.to_thread(analyze_stems, stems, beats_per_bar, 4, bpm_hint)
        ri = reference_index(files)
        structure_input = [stems[ri]] + [s for i, s in enumerate(stems) if i != ri]
    else:
        item["title"] = Path(item["file"]).stem
        analysis = await asyncio.to_thread(analyze, item["file"], beats_per_bar, 4, bpm_hint)
        structure_input = None
    # sections par SongFormer (composant optionnel) ; sinon / en cas d'échec : détection de ReaCue
    analysis, structure_info = await asyncio.to_thread(structure.apply_engine, analysis, structure_input,
                                                       item.get("title"))
    localize_analysis(analysis)
    opts = _new_options(count_in_bars=count_in_bars, tempo_mode=tempo_mode, click=click,
                        click_to_master=click_to_master, click_hw_output=click_hw_output,
                        cue_lead_bars=cue_lead_bars, song_region=song_region,
                        voice_cues=voice_cues, voice_count_in=voice_count_in,
                        voice_count_each=voice_count_each, voice_name=voice_name)
    summary = await _apply(analysis, item, opts, items)
    summary["file"] = item["file"]
    summary["structure_engine"] = structure_info
    summary["warnings"] = stem_warn + summary["warnings"]
    return summary


@mcp.tool()
@managed_job
async def analyze_audio(file_path: str, beats_per_bar: int | None = None, bpm_hint: float | None = None) -> dict:
    """Analyse seulement (sans toucher à REAPER) : BPM, mesure, stabilité du tempo, sections proposées."""
    from . import show_lock
    if show_lock.locked():
        return {"error": show_lock.message()}
    use_settings_lang()
    a = await asyncio.to_thread(analyze, str(Path(file_path).expanduser()), beats_per_bar, 4, bpm_hint)
    localize_analysis(a)
    return {"bpm": a.bpm, "signature": f"{a.beats_per_bar}/{a.denominator}", "bars": a.n_bars,
            "tempo_stable": a.tempo_stable, "tempo_cv": a.tempo_cv, "first_downbeat_s": a.downbeats[0],
            "sections": [{"name": s.name, "group": s.label, "bars": f"{s.start_bar + 1}-{s.end_bar}"}
                         for s in a.sections], "warnings": a.warnings}


@mcp.tool()
@managed_job
async def set_sections(sections: list[dict]) -> dict:
    """Corrige la structure du dernier morceau préparé et reconstruit régions, cues et click.
    Prioritaire : la liste donnée remplace la structure, y compris les régions modifiées à la main.

    sections : liste complète, dans l'ordre, de {"start_bar": int, "name": str}. start_bar commence à 1
    (1re mesure du morceau). Chaque section va jusqu'au début de la suivante.
    Exemple : [{"start_bar":1,"name":"Intro"},{"start_bar":9,"name":"Couplet 1"},{"start_bar":25,"name":"Refrain 1"}]
    Option : un élément {"prompteur_seul": true} (seul ou avec des sections) met à jour uniquement le
    prompteur des musiciens (paroles, accords, structure) sans rien modifier dans REAPER.
    Option : ajouter un élément {"grid": {"bpm": 168, "bar1_s": 8.6, "n_bars": 185}} pour imposer en même
    temps une grille à tempo constant (bar1_s = début de la mesure 1 dans le fichier de référence).
    Les noms de sections sont libres, en français ou en anglais (Verse, Chorus…).
    Mode concert : un élément {"concert": {"name": "Concert du 15/11", "songs": ["Song A", "Song B", …],
    "gap_s": 4, "live": ["drums", "bass"], "live_exceptions": {"Song B": {"bass": "stem"}}}} construit un
    projet concert à partir des projets déjà préparés de chaque morceau (même effet que build_concert) ; le
    dernier morceau préparé n'est pas modifié. « live » = instruments joués en vrai (leurs stems sont coupés).
    Profil « joué en live » d'un concert existant, sans le reconstruire : un élément
    {"concert_live": {"concert": "Concert du 15/11", "live": [...], "exceptions": {...}}} (même effet que
    set_live_profile).
    Export audio (ReaCue Studio), sans rien modifier dans REAPER : un élément {"export": {"stems": ["Basse"],
    "format": "mp3", "kbps": 320, "range": {"kind": "section", "section": "Refrain 1"} | {"kind": "bars",
    "from": 9, "to": 24} | {"kind": "song"}, "mode": "separate" | "mix", "click": false}} ; stems vides =
    tous. Fichiers dans <dossier du projet>/exports/ (et téléchargeables depuis la page studio.html).
    """
    from . import show_lock
    if show_lock.locked():
        return {"error": show_lock.message()}
    use_settings_lang()
    exp = next((d["export"] for d in sections if isinstance(d, dict) and isinstance(d.get("export"), dict)), None)
    if exp is not None:
        return await export_audio(exp)
    conc = next((d["concert"] for d in sections if isinstance(d, dict) and isinstance(d.get("concert"), dict)), None)
    if conc is not None:
        return await build_concert(conc.get("name") or "Concert", list(conc.get("songs") or []),
                                   float(conc.get("gap_s", 4.0)), conc.get("live"),
                                   conc.get("live_exceptions") or conc.get("exceptions"))
    prof = next((d["concert_live"] for d in sections if isinstance(d, dict)
                 and isinstance(d.get("concert_live"), dict)), None)
    if prof is not None:
        return await set_live_profile(prof.get("concert") or prof.get("name") or "", prof.get("live"),
                                      prof.get("exceptions") or prof.get("live_exceptions"),
                                      bool(prof.get("replace_exceptions")))
    a, item, opts, items = _load()
    # option : {"prompteur_seul": true} = republier seulement le prompteur, sans toucher à REAPER
    only = any(isinstance(d, dict) and (d.get("prompteur_seul") or d.get("publish_only")) for d in sections)
    sections = [d for d in sections if not (isinstance(d, dict) and ("prompteur_seul" in d or "publish_only" in d))]
    # option : {"grid": {"bpm": 168, "bar1_s": 8.6, "n_bars": 185}} dans la liste = grille imposée
    grid = next((d["grid"] for d in sections if isinstance(d, dict) and "grid" in d), None)
    sections = [d for d in sections if not (isinstance(d, dict) and "grid" in d)]
    if grid:
        _impose_grid(a, opts, float(grid["bpm"]), float(grid["bar1_s"]),
                     grid.get("n_bars"), grid.get("beats_per_bar"))
    if sections:
        a = resection(a, sections)
    if only:
        if sections or grid:
            _save(a, item, opts, items)
            return await _publish_only(a, item, opts, items)
        # prompteur seul : les régions modifiées à la main ne sont PAS reprises ici (le prompteur doit
        # rester d'accord avec les annonces et le click déjà dans REAPER) ; on le signale seulement
        _, changed, _ = await _from_regions(a, item, opts, items, adopt=False)
        res = await _publish_only(a, item, opts, items)
        if changed:
            res["warnings"].append(t("regions_changed_publish"))
        return res
    return await _apply(a, item, opts, items)


def _impose_grid(a, opts, bpm, bar1_s, n_bars=None, beats_per_bar=None):
    m = int(beats_per_bar or a.beats_per_bar)
    bar = 60.0 * m / bpm * (4 / a.denominator)
    if n_bars is None:
        n_bars = max(1, int((a.duration - bar1_s) // bar))
    n_bars = int(n_bars)
    a.beats_per_bar = m
    a.downbeats = [round(bar1_s + k * bar, 6) for k in range(n_bars + 1)]
    a.beats = [round(bar1_s + k * bar / m, 6) for k in range(n_bars * m + 1)]
    a.bpm, a.tempo_stable, a.tempo_cv = round(bpm, 4), True, 0.0
    a.alt_bpm = None
    a.warnings = [w for w in a.warnings if "tempo" not in w.lower() and "pulsation" not in w.lower()]
    opts.tempo_mode = "constant"
    return n_bars


@mcp.tool()
@managed_job
async def set_grid(
    bpm: float,
    bar1_s: float,
    n_bars: int | None = None,
    beats_per_bar: int | None = None,
    sections: list[dict] | None = None,
) -> dict:
    """Impose une grille à tempo constant quand l'analyse automatique s'est trompée, puis reconstruit tout.

    bpm : tempo exact (noires/min). bar1_s : début de la mesure 1, en secondes DANS LE FICHIER audio de
    référence (la batterie en mode stems, sinon le fichier analysé). n_bars : nombre de mesures (défaut :
    jusqu'à la fin du fichier). beats_per_bar : garder la mesure actuelle si absent.
    sections : nouvelle structure dans la numérotation de CETTE grille (même format que set_sections) ;
    fortement conseillé, car les anciennes mesures ne correspondent plus.
    """
    from . import show_lock
    if show_lock.locked():
        return {"error": show_lock.message()}
    use_settings_lang()
    a, item, opts, items = _load()
    n_bars = _impose_grid(a, opts, bpm, bar1_s, n_bars, beats_per_bar)
    if sections:
        a = resection(a, sections)
    else:
        for s in a.sections:            # au minimum, ne pas dépasser la nouvelle grille
            s.start_bar, s.end_bar = min(s.start_bar, n_bars - 1), min(s.end_bar, n_bars)
        a.sections = [s for s in a.sections if s.end_bar > s.start_bar]
    return await _apply(a, item, opts, items)


@mcp.tool()
@managed_job
async def rename_section(index: int, name: str) -> dict:
    """Renomme la section n° index (1 = première) du dernier morceau préparé."""
    from . import show_lock
    if show_lock.locked():
        return {"error": show_lock.message()}
    use_settings_lang()
    a, item, opts, items = _load()
    a, changed, warns = await _from_regions(a, item, opts, items)     # numéros = régions actuelles
    if not 1 <= index <= len(a.sections):
        return {"error": t("n_sections", n=len(a.sections))}
    a.sections[index - 1].name = name
    res = await _apply(a, item, opts, items)
    if changed:
        res["structure_from_regions"] = True
    res["warnings"] = warns + res.get("warnings", [])
    return res


@mcp.tool()
@managed_job
async def update_options(
    count_in_bars: int | None = None,
    tempo_mode: Literal["auto", "constant", "beatmap"] | None = None,
    click: bool | None = None,
    click_to_master: bool | None = None,
    click_hw_output: int | None = None,
    cue_lead_bars: int | None = None,
    song_region: bool | None = None,
    voice_cues: bool | None = None,
    voice_count_in: bool | None = None,
    voice_count_each: bool | None = None,
    voice_name: str | None = None,
    count_lang: Literal["en", "fr"] | None = None,
    count_voice: str | None = None,
    count_rate: int | None = None,
    count_anticipation_ms: float | None = None,
) -> dict:
    """Change des réglages (appels vocaux et voix compris, count-in, mode de tempo, click…) et reconstruit sans réanalyser l'audio.
    Les régions modifiées à la main dans REAPER sont reprises comme structure (structure_from_regions)."""
    from . import show_lock
    if show_lock.locked():
        return {"error": show_lock.message()}
    use_settings_lang()
    a, item, opts, items = _load()
    for k, v in locals().copy().items():
        if k not in ("a", "item", "opts") and v is not None and hasattr(opts, k):
            setattr(opts, k, v)
    return await _apply_from_regions(a, item, opts, items)


@mcp.tool()
async def get_project_state() -> dict:
    """Liste régions, marqueurs, marqueurs de tempo et pistes du projet REAPER courant."""
    return await bridge.call("get_state")


@mcp.tool()
async def goto_section(name: str | None = None, index: int | None = None) -> dict:
    """Place le curseur au début d'une région (par nom ou numéro de région REAPER)."""
    return await bridge.call("goto_region", {"name": name, "index": index})


@mcp.tool()
async def transport(action: Literal["play", "stop", "pause"]) -> dict:
    """Lecture / stop / pause dans REAPER."""
    return await bridge.call("transport", {"action": action})


def _spawn_concert_extras(setlist: Path):
    """Accords, paroles, batterie et entrées par morceau : calcul long, lancé en arrière-plan."""
    import subprocess
    import sys
    log = BRIDGE_DIR / "cli.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parent.parent
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        kw["start_new_session"] = True
    with open(log, "a", encoding="utf-8") as f:
        subprocess.Popen([sys.executable, "-m", "reacue_mcp.cli", "concert-extras", "--setlist", str(setlist),
                          "--resource-dir", str(BRIDGE_DIR.parent)],
                         cwd=str(root), stdout=f, stderr=f, stdin=subprocess.DEVNULL, **kw)


@mcp.tool()
@managed_job
async def build_concert(name: str, songs: list[str], gap_s: float = 4.0, live: list[str] | None = None,
                        live_exceptions: dict | None = None) -> dict:
    """Mode concert : enchaîne plusieurs morceaux DÉJÀ PRÉPARÉS dans un seul projet REAPER.

    name : nom du concert (fichier <dossier des concerts>/<name>.RPP ; réglage concert_dir,
    défaut <Documents>/REAPER Media/Concerts).
    songs : morceaux dans l'ordre, par nom de projet (« Demo Song ») ou chemin .RPP.
    gap_s : blanc minimum entre deux morceaux (arrondi à des mesures entières).
    Chaque morceau est repris de son projet (stems, tempo, structure validée, annonces, click) sans
    réanalyse. Le projet en cours n'est pas touché : dans REAPER, l'action « ReaCue - Concert » ouvre le
    concert dans un nouvel onglet, arrête la lecture à la fin de chaque morceau et place le curseur au
    début du suivant (Espace relance). Le prompteur suit tout le concert ; accords, paroles et batterie de
    chaque morceau s'ajoutent en arrière-plan (quelques minutes la première fois).
    live : instruments joués en vrai par le groupe (« Batterie », « bass »…) : leurs stems sont coupés sur
    tout le concert ; live_exceptions : exceptions par morceau, ex. {"Song B": {"bass": "stem"}} (la basse
    reste en stem sur ce morceau) ou {"Song C": ["keys"]} (inverse le profil pour ces instruments).
    Sans live : le profil déjà enregistré pour ce concert est gardé (reconstruction).
    """
    from . import show_lock
    if show_lock.locked():
        return {"error": show_lock.message()}
    use_settings_lang()
    from . import concert as conc
    try:
        res = await asyncio.to_thread(conc.build_concert, name, songs, gap_s, None, True, live, live_exceptions)
    except (FileNotFoundError, ValueError) as e:
        return {"error": str(e)}
    out = res.summary()
    try:
        _spawn_concert_extras(res.setlist)
        out["prompteur"] = t("concert_extras_spawned")
    except Exception as e:
        out["warnings"].append(t("concert_extras_not_spawned", e=e))
    out["ouvrir"] = t("concert_open_hint")
    return out


@mcp.tool()
@managed_job
async def set_live_profile(concert: str, live: list[str] | None = None, exceptions: dict | None = None,
                           replace_exceptions: bool = False) -> dict:
    """Mode concert : choisit quels stems sont coupés (« joué en live ») SANS reconstruire le concert.

    concert : nom du concert (ou chemin de son .RPP / .setlist.json).
    live : instruments joués en vrai par le groupe (ex. ["Batterie", "Basse", "Guitares", "Chant"]) ; leurs
    stems sont coupés ; None = garder le profil actuel ; [] = tous les stems joués.
    exceptions : par morceau, ex. {"Song B": {"bass": "stem"}} (stem de basse gardé sur ce morceau),
    {"Song C": {"keys": "live"}}, {"Song D": null} (retire les exceptions du morceau).
    replace_exceptions : True = remplace toutes les exceptions au lieu de les compléter.
    La fenêtre ReaCue (onglet Scène) applique le profil tout de suite ; il est gardé à la reconstruction.
    """
    from . import show_lock
    if show_lock.locked():
        return {"error": show_lock.message()}
    use_settings_lang()
    from . import concert as conc
    try:
        return await asyncio.to_thread(conc.set_live_profile, concert, live, exceptions, replace_exceptions)
    except (FileNotFoundError, ValueError) as e:
        return {"error": str(e)}


@mcp.tool()
@managed_job
async def new_song(files: list[str], title: str | None = None) -> dict:
    """Nouveau morceau : copie un fichier audio (MP3, WAV…), plusieurs stems ou un dossier de stems dans
    <dossier des projets>/<Titre>/ et crée le projet REAPER <Titre>.RPP (une piste par fichier, à 0 s).

    files : chemins sur l'ordinateur (un fichier, des stems, ou un dossier de stems).
    title : titre du morceau ; par défaut, déduit du nom (sans « -Bass- », tonalité, BPM, « Official Video »).
    Un projet existant n'est jamais écrasé. Ensuite : ouvrir le projet dans REAPER (fenêtre ReaCue, onglet
    Concert : clic sur le nom du morceau), puis « Séparer stems » (un seul fichier) et « Préparer ».
    """
    from . import show_lock
    if show_lock.locked():
        return {"error": show_lock.message()}
    use_settings_lang()
    from . import newsong as ns
    try:
        out = await asyncio.to_thread(ns.new_song, files, title)
    except (FileNotFoundError, ValueError, OSError) as e:
        return {"error": str(e)}
    out["open"] = t("new_song_open_hint")
    return out


def main():
    mcp.run()


if __name__ == "__main__":
    main()
