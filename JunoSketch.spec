# Build on macOS, using Python with Tk support.
a = Analysis(['main.py'], pathex=[], binaries=[], datas=[('assets/juno_ds_patches.json', 'assets')],
             hiddenimports=['mido.backends.rtmidi', 'rtmidi'], hookspath=[],
             hooksconfig={}, runtime_hooks=[], excludes=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='JunoSketch',
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='JunoSketch')
app = BUNDLE(coll, name='JunoSketch.app', icon=None,
             bundle_identifier='jp.junosketch.desktop',
             info_plist={'CFBundleShortVersionString': '0.1.6',
                         'NSHighResolutionCapable': True})
