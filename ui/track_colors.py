"""Shared track palette for editor layers, track list and overview."""
TRACK_COLORS = (
    '#55b4bb', '#e8ac60', '#ad94df', '#7ec684',
    '#df899c', '#7da9e5', '#cfbd69', '#a1c7b0',
    '#c39876', '#df8b63', '#8ea1ce', '#b8c77c',
    '#c58cc5', '#79bfcb', '#c7a2a9', '#99b5a0',
)


def track_color(index):
    return TRACK_COLORS[index % len(TRACK_COLORS)]


def ghost_color(index):
    color = track_color(index).lstrip('#')
    background = (32, 37, 45)
    return '#' + ''.join(f'{round(int(color[i:i+2], 16)*0.32 + background[i//2]*0.68):02x}'
                         for i in (0, 2, 4))


def project_end(project):
    return max((note.start + note.duration for track in project.tracks
                for note in track.notes), default=0)
