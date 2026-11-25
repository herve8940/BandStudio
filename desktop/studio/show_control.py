"""Write a portable QLab builder and grandMA3 import files from one clock."""
import csv
import hashlib
from pathlib import Path

# The standalone engine shares ReaCue's console-tested XML writer.
if (Path(__file__).parent/'tools/reacue_mcp/lighting.py').is_file():
    from tools.reacue_mcp import lighting
else:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from reacue_mcp import lighting
from show_export import LOCK_IN, smpte
from ui_language import ui_text


def literal(text):
    """AppleScript string literal; the project can contain arbitrary cue names."""
    text = ' '.join(str(text).splitlines()).replace('\\','\\\\').replace('"','\\"')
    return '"' + text + '"'


def qlab_script(songs, order, fps):
    source = ['''on run argv
    if (count argv) > 0 then
        set basePath to item 1 of argv
    else
        set basePath to POSIX path of (choose folder with prompt "BandStudio — choisir le dossier de régie / Choose show folder")
    end if
    if basePath does not end with "/" then set basePath to basePath & "/"
    set savePath to basePath & "Show.qlab5"
    set alreadySaved to false
    try
        set existingFile to (POSIX file savePath) as alias
        set alreadySaved to true
    end try
    if alreadySaved then error "Show.qlab5 existe déjà / already exists."
    tell application id "com.figure53.QLab.5"
        activate
        if (count of workspaces) is 0 then error "Ouvre un nouveau workspace vide dans QLab puis relance / Open a new empty workspace in QLab and run again."
        set ws to front workspace
        if (count of cue lists of ws) is not 1 then error "Un nouveau workspace vide est requis / Use a new empty workspace."
        set existingPath to missing value
        try
            set existingPath to path of ws
        end try
        if existingPath is not missing value and existingPath is not "" then error "Utilise un workspace vierge non enregistré / Use a new unsaved workspace."
        set mainList to current cue list of ws
        if (count of cues of mainList) is not 0 then error "Choisir un nouveau workspace vide / Choose a new empty workspace."
        with timeout of 3600 seconds''']
    def child(kind, name, wait=0):
        source.extend([f'set c to my addCue(ws, songGroup, "{kind}", {literal(name)})',
                       f'set pre wait of c to {wait:.8f}'])
    for key in order:
        song = songs[key]
        source.extend([f'set songGroup to my addCue(ws, mainList, "group", {literal(song["name"])})',
                       'set mode of songGroup to timeline'])
        child('timecode','LTC → grandMA3')
        source.extend(['set type of c to ltc','set audio output patch number of c to 0',
                       'set smpte format of c to '+{24:'fps_24',25:'fps_25',30:'fps_30_non_drop'}[fps],
                       f'set timecode start time of c to {literal(smpte(song["address"]*fps,fps))}',
                       f'set timecode end time of c to {literal(smpte(song["address"]*fps+song["frames"],fps))}'])
        tracks = list(song['items'])
        if song.get('mix'):
            tracks.insert(0,dict(file=song['mix'],role='mix',name='Façade / FOH',position=0,muted=False))
        for item in tracks:
            monitor = item['role'].startswith('guide_')
            child('audio', ('IEM · ' if monitor else '')+item['name'], LOCK_IN+item['position'])
            relative = song['directory']+'/'+item['file']
            source.append(f'set file target of c to (POSIX file (basePath & {literal(relative)}) as alias)')
            if monitor:
                source.append('set audio output patch number of c to 0')
            if item['muted'] or (song.get('mix') and item['role']!='mix' and not monitor):
                source.append('set armed of c to false')
        for cue in song['cues']:
            child('memo',cue['name'],cue['time'])
    source.append('''        end timeout
        set selected of ws to {first cue of mainList}
        save ws in (POSIX file savePath)
    end tell
end run

on addCue(ws, parentCue, cueKind, cueName)
    tell application id "com.figure53.QLab.5"
        make ws type cueKind
        set createdCue to last item of (selected of ws as list)
        set ident to uniqueID of createdCue
        set q name of createdCue to cueName
        set sourceParent to parent of createdCue
        if uniqueID of sourceParent is not uniqueID of parentCue then
            move cue id ident of sourceParent to end of parentCue
        end if
        return cue id ident of ws
    end tell
end addCue''')
    return '\n'.join(source)+'\n'


def write_control(bundle, title, songs, order, addresses, fps, layout, changed):
    import math
    from ui_language import using_english
    lang = 'en' if using_english() else 'fr'
    root = bundle/'grandMA3'/'gma3_library'/'datapools'
    seqdir, tcdir = root/'sequences', root/'timecodes'
    seqdir.mkdir(parents=True)
    tcdir.mkdir()
    tracks = []
    with (bundle/'Conduite.csv').open('w',encoding='utf-8-sig',newline='') as handle, (bundle/'Paroles-Accords.csv').open('w',encoding='utf-8-sig',newline='') as notes:
        rows, annotations = csv.writer(handle),csv.writer(notes)
        rows.writerow(['Titre / Song','Cue','Repère / Marker','GO + s','SMPTE', 'fps'])
        annotations.writerow(['Titre / Song','Type','Texte / Text','GO + s','SMPTE'])
        for song in songs.values():
            key = song['id']
            address = addresses[key]
            song.update(address=address,frames=math.ceil((song['duration']+LOCK_IN)*fps))
            markers = list(song['markers']) or [dict(name=ui_text('Début','Start'),time=0,kind='cue')]
            names = lighting.unique([m['name'] for m in markers])
            codes = []
            for i,(m,name) in enumerate(zip(markers,names),1):
                frame = round((m['time']+LOCK_IN)*fps)
                codes.append(dict(name=name,time=frame/fps))
                rows.writerow([song['name'],i,name,frame/fps,smpte(address*fps+frame,fps),fps])
            for kind,entries in [('lyrics',song['lyrics']),('chords',song['chords'])]:
                for entry in entries:
                    for part in (entry.get('words') or [entry]):
                        frame = round((part['start']+song['lead']+LOCK_IN)*fps)
                        annotations.writerow([song['name'],kind,part.get('text',''),frame/fps,smpte(address*fps+frame,fps)])
            # Names are stable for songs with identical display titles and when reordered.
            suffix = hashlib.sha256(key.encode()).hexdigest()[:8]
            seq = lighting.clean_name(song['name'])[:36]+'_'+suffix
            (seqdir/(seq+'.xml')).write_text(lighting.build_sequence_xml(seq,codes,lang), encoding='utf-8')
            song['cues'] = codes
            track = dict(seq=seq,start=address,duration=song['frames']/fps,cues=codes)
            tracks.append(track)
            if layout in ('songs','both'):
                write_timecode(tcdir,'TC_'+seq,[track],lang)
    if layout in ('concert','both'):
        write_timecode(tcdir,'Concert_'+lighting.clean_name(title)[:44],tracks,lang)
    (bundle/'Build QLab.applescript').write_text(qlab_script(songs,order,fps),encoding='utf-8')
    launcher = bundle/'Build QLab.command'
    launcher.write_text('#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\nexec /usr/bin/osascript "Build QLab.applescript" "$PWD"\n',encoding='utf-8')
    launcher.chmod(0o755)
    (bundle/'README.txt').write_text(ui_text(
        f'Crée un nouveau workspace vide dans QLab 5, puis ouvre Build QLab.command sur le Mac pour créer Show.qlab5. Depuis Windows, copie tout le dossier sur le Mac. Si le double-clic est indisponible, ouvre Build QLab.applescript dans Éditeur de scripts, lance-le et sélectionne ce dossier. Utilise une licence QLab avec les sorties audio nécessaires.\\n'
        f'Assigne la façade, les retours IEM et le LTC à leurs sorties. Les guides et le LTC arrivent sans sortie affectée. Dans le mode mix + pistes, le mix est actif et les pistes de façade sont désarmées. Pour jouer sur pistes, désarme le mix et arme les pistes souhaitées. Les mémos indiquent où placer les cues vidéo.\\n'
        f'grandMA3 : copie gma3_library dans grandMA3 sur la clé USB. Importe les séquences puis le ou les Timecode Shows dans le DataPool Default. Choisis un slot externe, assigne-lui l’entrée LTC et mets en lecture le Timecode Show voulu. Cadence {fps} i/s. Une seule conduite en lecture. Pour une nouvelle version, importe d’abord dans une copie du show afin de conserver les ambiances programmées.\\n'
        f'GO lance le LTC, puis les bandes après {LOCK_IN} secondes de synchronisation. Répète le routage, le départ et la reprise avec la console avant le concert.',
        f'Create a new empty workspace in QLab 5, then open Build QLab.command on the Mac to create Show.qlab5. From Windows copy the entire folder. Alternatively run Build QLab.applescript in Script Editor and choose this folder. Use a QLab license supporting your audio outputs.\\n'
        f'Patch FOH, IEM and LTC to their respective outputs. Guides and LTC start unpatched. In mix + stems mode FOH stems are disarmed. Disarm the mix before arming the desired FOH stems. Memos mark video cue positions.\\n'
        f'grandMA3: copy gma3_library into grandMA3 on the USB drive. Import sequences then the Timecode Shows into the Default DataPool. Assign LTC input and the desired show to the same external slot. Play one timecode show at a time. Import revisions into a copy of your show to preserve programmed looks. Frame rate {fps} fps.\\n'
        f'GO starts LTC, followed by audio after {LOCK_IN} seconds for lock. Rehearse routing, start and restart with the console.'
    ).replace('\\n','\n')+'\n',encoding='utf-8')

    if changed:
        with (bundle/'README.txt').open('a',encoding='utf-8') as guide:
            for key,old in changed.items():
                guide.write(ui_text('Morceau rallongé, vérifier la nouvelle plage LTC : ', 'Song extended, check the new LTC range: ')
                            + songs[key]['name'] + ' · ' + smpte(old*fps,fps) + ' → ' + smpte(addresses[key]*fps,fps) + '\n')


def write_timecode(folder, name, tracks, lang):
    xml = lighting.build_timecode_xml(tracks, lang)
    xml = xml.replace('<Timecode Name=""', '<Timecode Name="' + lighting.escape_xml(name) + '"', 1)
    (folder/(name+'.xml')).write_text(xml, encoding='utf-8')
