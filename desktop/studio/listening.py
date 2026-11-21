"""Instrument groups shared by preview, project validation and REAPER exports."""
INSTRUMENTS = ('drums', 'bass', 'vocals', 'guitar', 'piano', 'other', 'vocal_lead', 'vocal_backing', 'drum_kick', 'drum_snare', 'drum_toms', 'drum_cymbals', 'take')

def parse_mode(mode):
    if mode in ('original', 'mix'): return mode, None
    if mode == 'minus': return 'minus', 'drums'
    if mode == 'drums': return 'solo', 'drums'
    if isinstance(mode, str):
        kind, _, role = mode.partition(':')
        if kind in ('minus', 'solo') and role in INSTRUMENTS: return kind, role
    raise ValueError('Mode d’écoute invalide.')

def matches(role, instrument):
    return role == instrument or (instrument == 'drums' and role.startswith('drum_')) or (instrument == 'vocals' and role.startswith('vocal_'))

def included(role, mode):
    kind, instrument = parse_mode(mode)
    return not matches(role, instrument) if kind == 'minus' else matches(role, instrument) if kind == 'solo' else True


def guide_audible(project, role):
    """Apply the track mute/solo bus to guides, including count-in voices."""
    tracks = project['tracks']
    guide = next((t for t in tracks if t['role'] == role), {})
    has_solo = any(t.get('solo', False) for t in tracks if t['role'] != 'source')
    return not guide.get('muted', False) and (not has_solo or guide.get('solo', False))
