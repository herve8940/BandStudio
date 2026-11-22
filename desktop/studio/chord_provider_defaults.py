"""Chord publishers shared by workers, native installers and code-only updates."""
import json
from pathlib import Path

CATALOG_VERSION = 10
PROVIDERS = [{'id': 'cifraclub',
  'publisher': 'Cifra Club',
  'domain': 'cifraclub.com',
  'template': 'https://www.cifraclub.com/{artist}/{title}/'},
 {'id': 'echords',
  'publisher': 'E-Chords',
  'domain': 'e-chords.com',
  'template': 'https://www.e-chords.com/chords/{artist}/{title}'},
 {'id': 'explorer',
  'publisher': 'GuitarTabsExplorer',
  'domain': 'guitartabsexplorer.com',
  'template': 'https://www.guitartabsexplorer.com/{artist}/{title}-chords'},
 {'id': 'topaccords',
  'publisher': 'TopAccords',
  'domain': 'topaccords.com',
  'template': 'https://www.topaccords.com/partition/{artist}/{title}'},
 {'id': 'acordesweb',
  'publisher': 'AcordesWeb',
  'domain': 'acordesweb.com',
  'template': 'https://acordesweb.com/cancion/{artist}/{title}'},
 {'id': 'chordsworld',
  'publisher': 'ChordsWorld',
  'domain': 'chordsworld.com',
  'template': 'https://chordsworld.com/{artist}-{title}-chords/'},
 {'id': 'khmerchords',
  'publisher': 'KhmerChords',
  'domain': 'khmerchords.com',
  'template': 'https://www.khmerchords.com/en/{artist}/{title}'},
 {'id': 'chordsandtabs',
  'publisher': 'Chords and Tabs',
  'domain': 'chords-and-tabs.net',
  'template': 'https://www.chords-and-tabs.net/song/name/{artist}-{title}'},
 {'id': 'ukuleletabs',
  'publisher': 'Ukulele Tabs',
  'domain': 'ukulele-tabs.com',
  'template': 'https://www.ukulele-tabs.com/uke-songs/{artist}-uke-tabs.html'},
 {'id': 'ultimate', 'publisher': 'Ultimate Guitar', 'domain': 'ultimate-guitar.com'},
 {'id': 'songsterr', 'publisher': 'Songsterr', 'domain': 'songsterr.com'},
 {'id': 'boite', 'publisher': 'La Boîte à chansons', 'domain': 'boiteachansons.net'},
 {'id': 'tabs4acoustic', 'publisher': 'Tabs4Acoustic', 'domain': 'tabs4acoustic.com'},
 {'id': 'chordie', 'publisher': 'Chordie', 'domain': 'chordie.com'},
 {'id': 'lacuerda', 'publisher': 'LaCuerda', 'domain': 'lacuerda.net'},
 {'id': 'justinguitar', 'publisher': 'JustinGuitar', 'domain': 'justinguitar.com'},
 {'id': 'chordify', 'publisher': 'Chordify', 'domain': 'chordify.net'},
 {'id': 'ukutabs', 'publisher': 'UkuTabs', 'domain': 'ukutabs.com'},
 {'id': 'guitartwitt', 'publisher': 'GuitarTwitt', 'domain': 'guitartwitt.com'},
 {'id': 'guitaretab', 'publisher': 'GuitareTab', 'domain': 'guitaretab.com'},
 {'id': 'guitartabs', 'publisher': 'GuitarTabs.cc', 'domain': 'guitartabs.cc'},
 {'id': 'azchords', 'publisher': 'AZChords', 'domain': 'azchords.com'},
 {'id': '911tabs', 'publisher': '911Tabs', 'domain': '911tabs.com'}]


def write_catalog(folder):
    path = Path(folder) / 'chord-providers.json'
    path.write_text(json.dumps(PROVIDERS, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return path
