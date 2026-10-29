"""Playback audibility; mute takes priority over solo."""


def audible_tracks(tracks):
    soloed = any(track.solo for track in tracks)
    return tuple(not track.muted and (not soloed or track.solo) for track in tracks)
