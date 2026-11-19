"""Temporary diagnostic: full lookup from real downloaded-file names, after the fix."""
import sys,ssl,platform
sys.path.insert(0,'desktop/studio')
import chord_sources as cs
print('python',sys.version.split()[0],'|',platform.platform())
names=['Full_Oasis - Wonderwall (128kbit_AAC)','Full_The Beatles - Let It Be (128kbit_AAC)','Full_Eagles - Hotel California (128kbit_AAC)',
       "Full_Bob Dylan - Knockin' On Heaven's Door (128kbit_AAC)",'Full_The Cranberries - Zombie (Official Music Video) (128kbit_AAC)',
       'Full_Last Train - Between Wounds (128kbit_AAC)']
for n in names:
    r=cs.lookup({'name':n},reanalyze=True)['reference']
    print(f"{n:68} -> {r['query']!r:40} {r['status']:10} {len(r['sources'])} grille(s) {[c['id']+':'+c['status'] for c in r['checks']]}")
