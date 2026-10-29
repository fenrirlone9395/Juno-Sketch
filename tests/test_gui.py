import os
import sys
from types import SimpleNamespace as NS
import pytest
pytestmark=pytest.mark.skipif(sys.platform != 'darwin' and not os.environ.get('DISPLAY'),reason='GUI display unavailable')

def test_window_and_real_canvas(tmp_path):
    from ui.main_window import MainWindow
    from services.project_io import load
    from test_core import Capture
    app=MainWindow()
    try:
        app.output=Capture()
        app.update()
        assert app.list.size()==16
        r=app.roll
        r.canvas.yview_moveto(0)
        app.update()
        y=r.TOP+(127-100)*r.ROW+5
        r.double(NS(x=r.KEY+10,y=y,state=0))
        app.update()
        assert len(app.track.notes)==1
        assert r.canvas.find_withtag('note')
        app.path=tmp_path/'gui.juno.json'
        app.save()
        assert load(app.path).tracks[0].notes[0].pitch==100
        app.undo();assert not app.track.notes
        app.redo();assert app.track.notes
        app.project.ui['selected']=15;app.sync_ui();app.update()
        assert app.list.curselection()==(15,)
        app.update_idletasks()
    finally:
        app.stop();app.release_output();app.destroy()


def test_layers_and_all_track_playback_view(tmp_path):
    from ui.main_window import MainWindow
    from models.project import Note, Project
    from services.project_io import load
    app=MainWindow()
    try:
        for i, track in enumerate(app.project.tracks):
            track.notes=[Note(i*240,60+i,240)]
        app.project.tracks[15].notes.append(Note(40*3840,80,960))
        app.sync_ui();app.update()
        r=app.roll
        assert len(r.canvas.find_withtag('ghost'))==16
        assert len(r.canvas.find_withtag('note'))==1
        ghost=app.project.tracks[1].notes[0]
        x,y,_,_=r.coords(ghost)
        assert r.hit(x+1,y+1) is None
        # A non-active long phrase expands the shared timeline, too.
        assert float(r.canvas.cget('scrollregion').split()[2])>40*3840*r.SCALE
        app.ghost_var.set(False);app.layer_change()
        assert not r.canvas.find_withtag('ghost')
        app.ghost_var.set(True);app.layer_change()
        app.view_var.set('All Tracks');app.view_change();app.update()
        o=app.overview
        assert o.winfo_ismapped() and not r.winfo_ismapped()
        assert len(o.canvas.find_withtag('lane'))==16
        assert len(o.canvas.find_withtag('overview_note'))==17
        assert all(o.canvas.find_withtag(f'track_{i}') for i in range(16))
        # The playback view has no note edit gesture.
        before=app.project.data()['tracks']
        app.focus_set();app.delete_key(NS())
        assert app.project.data()['tracks']==before
        app.player.playing=True
        app.player.cursor=lambda:80000
        app.draw_cursors(80000)
        assert o.canvas.xview()[0]>0
        assert app.player.playing
        app.player.playing=False
        app.path=tmp_path/'layers.juno.json';app.save()
        restored=load(app.path)
        assert restored.ui['view']=='All Tracks' and restored.ui['show_ghosts']
        assert restored.ui['overview_xview']>0
        # Double click a lane returns to that track for editing.
        o.edit(NS(y=o.lane_height()*15+.5))
        app.update()
        assert app.project.ui['selected']==15
        assert app.project.ui['view']=='Piano Roll'
        assert r.winfo_ismapped()
        assert len(r.canvas.find_withtag('note'))==2
        assert len(r.canvas.find_withtag('ghost'))==15
        # Old v0.1 projects gain safe display defaults.
        data=Project().data()
        for key in ('view','show_ghosts','follow_playhead'):data['ui'].pop(key)
        assert Project.from_data(data).ui['view']=='Piano Roll'
    finally:
        app.player.playing=False
        app.stop();app.release_output();app.destroy()


def test_apply_patch_name_and_auto_follow():
    from ui.main_window import MainWindow
    from test_core import Capture
    app=MainWindow()
    try:
        out=Capture();app.output=out
        app.fields['msb'].set('87');app.fields['lsb'].set('73');app.fields['program'].set('1')
        assert 'Grand Pno DS' in app.patch_label.get()
        app.apply_patch_name()
        assert app.track.name=='Grand Pno DS'
        assert not out.messages  # Renaming does not require hardware or sound output.
        assert 'Grand Pno DS' in app.list.get(0)
        app.auto_name_var.set(True);app.naming_change()
        app.fields['program'].set('2');app.apply_track()
        assert app.track.name=='Rock Pno DS'
        app.auto_name_var.set(False);app.naming_change()
        app.name_var.set('My Piano');app.fields['program'].set('3');app.apply_track()
        assert app.track.name=='My Piano'
        app.fields['msb'].set('0');app.apply_patch_name()
        assert app.track.name=='My Piano'
        app.undo()
        assert app.track.program==1
    finally:
        app.stop();app.release_output();app.destroy()


def test_destination_switch_sends_all_tracks_and_port_changes_preserve_banks(monkeypatch):
    import ui.main_window as window
    from test_core import Capture
    outputs=[]
    def opened(*args):
        out=Capture();outputs.append(out);return out
    monkeypatch.setattr(window,'InternalPreviewOutput',opened)
    monkeypatch.setattr(window,'JunoDsOutput',opened)
    app=window.MainWindow()
    try:
        app.track.auto_name=True
        app.output_var.set('JUNO-DS');app.output_change()
        assert (app.track.msb,app.track.lsb)==(87,64)
        assert not outputs  # No implicit/default USB port selection.
        app.port.set('JUNO USB');app.output_change()
        assert len(outputs[-1].messages)==48
        assert outputs[-1].messages[0].value==87
        assert outputs[-1].messages[9*3].value==86
        app.track.msb,app.track.lsb=87,73
        app.port.set('JUNO USB 2');app.output_change()
        assert app.track.lsb==73
        app.output_var.set('Internal Preview');app.output_change()
        assert (app.track.msb,app.track.lsb)==(121,0)
        assert app.track.name=='Piano 1'
        assert outputs[-1].messages[0].value==121
        assert outputs[-1].messages[9*3].value==120
        assert app.fields['msb'].get()=='121'
        assert 'GM:' in app.patch_label.get()
        app.undo()
        assert app.project.ui['output']=='JUNO-DS'
        assert app.track.lsb==73
        app.redo()
        assert app.project.ui['output']=='Internal Preview'
        assert app.track.msb==121
    finally:
        app.stop();app.release_output();app.destroy()
