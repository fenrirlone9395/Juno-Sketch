"""JUNO-DS factory patch names, keyed by CC0, CC32 and wire Program Change."""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def patch_map():
    path = Path(__file__).resolve().parent.parent / 'assets' / 'juno_ds_patches.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    return {(p['msb'], p['lsb'], p['program']): p for p in data['patches']}


def lookup(msb, lsb, program):
    """Return a known factory patch, or None. Program is zero-based."""
    return patch_map().get((msb, lsb, program))


def apply_name(track):
    patch = lookup(track.msb, track.lsb, track.program)
    if patch is None:
        return False
    track.name = patch['name']
    return True
