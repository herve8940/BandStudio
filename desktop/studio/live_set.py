"""Write portable Live 11 Arrangement sets. All audio clips play at native speed."""
from bisect import bisect_right
from copy import deepcopy
import gzip
from itertools import count
from pathlib import Path
import xml.etree.ElementTree as ET

import soundfile as sf

def asset(name):
    source = Path(__file__).with_name('export_assets') / name
    return source if source.exists() else Path(__file__).parent / 'tools/show_assets' / (name + '.txt')


def value(element, path, number):
    element.find(path).set('Value', str(number))


def tempo_automation(song, points):
    seconds = [point['time'] for point in points]
    beats = [0.]
    for previous, current in zip(points, points[1:]):
        beats.append(beats[-1] + (current['time'] - previous['time']) * previous['bpm'] / 60)

    def beat_at(time):
        index = max(0, bisect_right(seconds, time) - 1)
        return beats[index] + (time - seconds[index]) * points[index]['bpm'] / 60

    mixer = song.find('MasterTrack/DeviceChain/Mixer')
    envelopes = song.findall('MasterTrack/AutomationEnvelopes/Envelopes/AutomationEnvelope')
    for parameter, tag in [('Tempo', 'FloatEvent'), ('TimeSignature', 'EnumEvent')]:
        knob = mixer.find(parameter)
        target = knob.find('AutomationTarget').get('Id')
        envelope = next(e for e in envelopes if e.find('EnvelopeTarget/PointeeId').get('Value') == target)
        events = envelope.find('Automation/Events')
        events.clear()
        previous = None
        for index, point in enumerate(points):
            if parameter == 'TimeSignature' and not point['flags']:
                continue
            number = (point['bpm'] if parameter == 'Tempo' else
                      (point['denominator'].bit_length() - 1) * 99 + point['numerator'] - 1)
            if index == 0:
                value(knob, 'Manual', number)
            elif number == previous:
                continue
            # Two nodes at the breakpoint keep REAPER's square tempo changes.
            if index and parameter == 'Tempo':
                ET.SubElement(events, tag, Id=str(len(events)), Time=str(beats[index]), Value=str(previous))
            ET.SubElement(events, tag, Id=str(len(events)), Time=str(beats[index] if index else -63072000),
                          Value=str(number))
            previous = number
    return beat_at


def write_live_set(folder, filename, items, markers, points, duration):
    document = ET.parse(asset('live11-set.xml'))
    song = document.getroot().find('LiveSet')
    tracks = song.find('Tracks')
    prototype = tracks[0]
    tracks.remove(prototype)
    clip_model = ET.parse(asset('live11-clip.xml')).getroot()
    ids = count(int(song.find('NextPointeeId').get('Value')))
    beat_at = tempo_automation(song, points)
    for index, item in enumerate(items):
        track = deepcopy(prototype)
        tracks.append(track)
        track.set('Id', str(next(ids)))
        for node in track.iter():
            if node.tag == 'Pointee' or node.tag.endswith('Target') and 'Id' in node.attrib:
                node.set('Id', str(next(ids)))
        for key in ('EffectiveName', 'UserName'):
            value(track, 'Name/' + key, item['name'])
        mixer = track.find('DeviceChain/Mixer')
        value(mixer, 'Speaker/Manual', str(not item['muted']).lower())
        value(mixer, 'Pan/Manual', item['pan'])
        value(mixer, 'Volume/Manual', item['gain'])
        value(track, 'Color', index % 64)
        clip = deepcopy(clip_model)
        track.find('DeviceChain/MainSequencer/Sample/ArrangerAutomation/Events').append(clip)
        info = sf.info(folder / item['file'])
        start = beat_at(item['position'])
        end = beat_at(item['position'] + info.duration)
        clip.set('Id', str(next(ids)))
        clip.set('Time', str(start))
        for path, number in [('CurrentStart', start), ('CurrentEnd', end), ('Name', item['name']),
                             ('Color', index % 64), ('Loop/LoopEnd', info.duration),
                             ('Loop/OutMarker', info.duration), ('Loop/HiddenLoopEnd', info.duration),
                             ('ScrollerTimePreserver/RightTime', info.duration),
                             ('SampleRef/FileRef/RelativePath', item['file']),
                             ('SampleRef/FileRef/OriginalFileSize', (folder / item['file']).stat().st_size),
                             ('SampleRef/LastModDate', 0), ('SampleRef/DefaultDuration', info.frames),
                             ('SampleRef/DefaultSampleRate', info.samplerate)]:
            value(clip, path, number)
        warp = clip.find('WarpMarkers')
        ET.SubElement(warp, 'WarpMarker', Id='0', SecTime='0', BeatTime='0')
        ET.SubElement(warp, 'WarpMarker', Id='1', SecTime=str(info.duration), BeatTime=str(end-start))
    locators = song.find('Locators/Locators')
    for marker in markers:
        loc = ET.SubElement(locators, 'Locator', Id=str(next(ids)))
        for key, val in [('LomId', 0), ('Time', beat_at(marker['time'])), ('Name', marker['name']),
                         ('Annotation', ''), ('IsSongStart', 'false')]:
            ET.SubElement(loc, key, Value=str(val))
    value(song, 'Transport/LoopLength', beat_at(duration))
    value(song, 'NextPointeeId', next(ids))
    (folder / 'Ableton Project Info').mkdir(exist_ok=True)
    path = folder / filename
    with gzip.open(path, 'wb') as out:
        document.write(out, encoding='UTF-8', xml_declaration=True)
    return path
