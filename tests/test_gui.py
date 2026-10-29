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


def test_meter_edit_updates_both_views_without_moving_notes():
    from ui.main_window import MainWindow
    from models.project import Note
    app=MainWindow()
    try:
        app.track.notes=[Note(3000,60,240)]
        app.change_meter(1,3,4);app.update()
        assert app.project.signatures==[[0,3,4]]
        assert app.track.notes[0].start==3000
        def texts(canvas):
            return [canvas.itemcget(i,'text') for i in canvas.find_all() if canvas.type(i)=='text']
        assert '2|1' in texts(app.roll.ruler)
        labels=[i for i in app.roll.ruler.find_all() if app.roll.ruler.type(i)=='text' and app.roll.ruler.itemcget(i,'text')=='2|1']
        assert app.roll.ruler.coords(labels[0])[0]==pytest.approx(app.roll.KEY+2880*app.roll.SCALE+3)
        app.view_var.set('All Tracks');app.view_change();app.update()
        assert '2|1' in texts(app.overview.ruler)
        app.change_meter(5,6,8)
        assert app.project.signatures==[[0,3,4],[11520,6,8]]
        app.undo();assert app.project.signatures==[[0,3,4]]
        app.redo();assert app.project.signatures[-1]==[11520,6,8]
        app.meter_dialog();app.update()
        dialogs=[w for w in app.winfo_children() if w.winfo_class()=='Toplevel']
        assert dialogs
        for d in dialogs:d.destroy()
    finally:
        app.stop();app.release_output();app.destroy()


def test_real_shift_track_selection_bulk_names_and_states():
    from ui.main_window import MainWindow
    from test_core import Capture
    app=MainWindow()
    try:
        out=Capture();app.output=out
        app.update()
        for index in (1,4):
            _,y,_,height=app.list.bbox(index)
            state=1 if index==4 else 0
            app.list.event_generate('<ButtonPress-1>',x=10,y=y+height//2,state=state)
            app.list.event_generate('<ButtonRelease-1>',x=10,y=y+height//2,state=state)
            app.update()
        assert app.list.curselection()==(1,2,3,4)
        assert app.selected_track_indices()==[1,2,3,4]
        assert app.project.ui['selected']==4
        for i in (1,2,3,4):app.project.tracks[i].name=f'Custom {i}'
        app.project.tracks[2].program=24
        app.project.tracks[3].msb=0
        app.project.tracks[4].program=40
        app.sync_ui()
        before=[(t.channel,t.msb,t.lsb,t.program) for t in app.project.tracks]
        count=len(app.history.past)
        app.patch_name_button.invoke()
        assert [app.project.tracks[i].name for i in (1,2,3,4)]==['Piano 1','Nylon-str.Gt','Custom 3','Violin']
        assert len(app.history.past)==count+1
        assert before==[(t.channel,t.msb,t.lsb,t.program) for t in app.project.tracks]
        assert not out.messages
        app.undo()
        assert [app.project.tracks[i].name for i in (1,2,3,4)]==[f'Custom {i}' for i in (1,2,3,4)]
        app.solo_button.invoke()
        assert all(app.project.tracks[i].solo for i in (1,2,3,4))
        app.mute_button.invoke()
        assert all(app.project.tracks[i].muted for i in (1,2,3,4))
        app.mute_button.invoke()
        assert not any(app.project.tracks[i].muted for i in (1,2,3,4))
        assert app.list.curselection()==(1,2,3,4)
    finally:
        app.stop();app.release_output();app.destroy()


def test_keyboard_and_note_click_preview_with_real_output_capture():
    from ui.main_window import MainWindow
    from models.project import Note
    from test_core import Capture
    app=MainWindow()
    try:
        out=Capture();app.output=out;app.update()
        r=app.roll
        y=r.TOP+(127-60)*r.ROW-r.canvas.canvasy(0)+r.ROW//2
        r.key_down(NS(y=y));app.update()
        assert app.audition_note==(0,60)
        assert r.preview_pitch==60
        assert not app.track.notes
        r.key_motion(NS(y=y-r.ROW))
        assert app.audition_note==(0,61)
        r.key_up()
        assert app.audition_note is None
        assert [(m.type,m.note) for m in out.messages if m.type in ('note_on','note_off')]==[
            ('note_on',60),('note_off',60),('note_on',61),('note_off',61)]
        app.track.notes=[Note(240,60,240,78)];r.redraw()
        r.down(NS(x=r.KEY+240*r.SCALE+4,y=y,state=0));r.up(NS())
        assert app.audition_note==(0,60)
        assert out.messages[-1].type=='note_on' and out.messages[-1].velocity==78
        app.end_audition()
        assert out.messages[-1].type=='note_off'
    finally:
        app.stop();app.release_output();app.destroy()


def test_zoom_anchor_scroll_synchronization_and_saved_ui(tmp_path):
    from ui.main_window import MainWindow
    from services.project_io import load
    app=MainWindow()
    try:
        app.update();r=app.roll
        r.canvas.xview_moveto(.2);r.canvas.yview_moveto(.4);app.update()
        sx=r.KEY+(r.canvas.winfo_width()-r.KEY)/2;sy=r.canvas.winfo_height()/2
        tick=(r.canvas.canvasx(sx)-r.KEY)/r.SCALE
        pitch_row=(r.canvas.canvasy(sy)-r.TOP)/r.ROW
        r.zoom(horizontal=1.25,vertical=1.25);app.update()
        assert (r.canvas.canvasx(sx)-r.KEY)/r.SCALE==pytest.approx(tick,abs=15)
        assert (r.canvas.canvasy(sy)-r.TOP)/r.ROW==pytest.approx(pitch_row,abs=.1)
        assert r.ROW==20 and r.SCALE==pytest.approx(.125)
        left=r.canvas.canvasx(0)
        r.keys.event_generate('<Shift-MouseWheel>',delta=-3);app.update()
        assert r.canvas.canvasx(0)>left
        assert r.velocity.xview()[0]==pytest.approx(r.canvas.xview()[0],abs=.001)
        left=r.canvas.canvasx(0)
        r.horizontal_wheel.set(True);r.wheel_mode_changed()
        r.wheel(NS(delta=-3,state=0,num=None));app.update()
        assert r.canvas.canvasx(0)>left
        app.path=tmp_path/'zoom.juno.json';app.save()
        q=load(app.path)
        assert q.ui['zoom_x']==1.25 and q.ui['zoom_y']==1.25 and q.ui['wheel_horizontal']
        r.zoom(reset=True)
        assert r.ROW==16 and r.SCALE==pytest.approx(.1)
    finally:
        app.stop();app.release_output();app.destroy()


def test_transport_keys_preempt_focused_controls_and_preserve_text():
    from ui.main_window import MainWindow
    from tkinter import ttk
    app=MainWindow()
    try:
        app.update()
        toggles=[]
        app.toggle=lambda:toggles.append('toggle')
        # A real class binding would toggle this checkbox without the early tag.
        for control in (app.ghost_button,app.solo_button,app.mute_button):
            control.focus_force();app.update()
            before=app.project.data()
            for sequence in ('<KeyPress-space>','<KeyRelease-space>'):
                control.event_generate(sequence);app.update()
            assert app.project.data()==before
        assert len(toggles)==3
        app.solo_button.invoke();app.update()
        assert app.track.solo and app.solo_button.cget('relief')=='sunken'
        app.solo_button.invoke();app.update()
        assert not app.track.solo and app.solo_button.cget('relief')=='raised'
        entries=[]
        def collect(w):
            if isinstance(w,ttk.Entry):entries.append(w)
            for c in w.winfo_children():collect(c)
        collect(app)
        entry=next(w for w in entries if str(w.cget('textvariable'))==str(app.name_var))
        entry.focus_force();app.update();entry.icursor('end')
        old=entry.get()
        entry.event_generate('<KeyPress-space>');entry.event_generate('<KeyRelease-space>');app.update()
        assert entry.get()==old+' ' and len(toggles)==3
    finally:
        app.stop();app.release_output();app.destroy()


def test_piano_roll_follow_and_return_to_start():
    from ui.main_window import MainWindow
    from models.project import Note
    app=MainWindow()
    try:
        app.track.notes=[Note(40*3840,60,960)]
        app.sync_ui();app.update();r=app.roll
        app.player.cursor=lambda:80000
        app.player.playing=True
        app.draw_cursors(80000);app.update()
        x=r.KEY+80000*r.SCALE
        assert r.canvas.canvasx(r.KEY)<=x<=r.canvas.canvasx(r.canvas.winfo_width()-20)
        assert r.velocity.xview()[0]==pytest.approx(r.canvas.xview()[0],abs=.001)
        r.xview('moveto',0);app.project.ui['follow_playhead']=False
        app.draw_cursors(80000);app.update()
        assert r.canvas.xview()[0]==0
        app.player.playing=False
        app.playhead=80000;r.xview('moveto',.3)
        r.selected={app.track.notes[0].id}
        r.canvas.focus_force();app.update()
        r.canvas.event_generate('<Return>');app.update()
        assert app.playhead==80000
        r.selected.clear()
        r.canvas.event_generate('<Return>');app.update()
        assert app.playhead==0 and app.player.position==0
        assert r.canvas.xview()[0]==0 and r.velocity.xview()[0]==0
        app.view_var.set('All Tracks');app.view_change();app.update()
        app.playhead=20000;app.overview.canvas.xview_moveto(.3)
        app.overview.canvas.focus_force();app.update()
        app.overview.canvas.event_generate('<Return>');app.update()
        assert app.playhead==0 and app.overview.canvas.xview()[0]==0
    finally:
        app.player.playing=False
        app.stop();app.release_output();app.destroy()


def test_solo_mute_shortcuts_and_input_protection():
    from ui.main_window import MainWindow
    from tkinter import ttk
    app=MainWindow()
    try:
        app.update();canvas=app.roll.canvas
        assert app.solo_button.cget('text')=='Solo'
        assert app.mute_button.cget('text')=='Mute'
        app.project.ui['track_selection']=[0,1];app.sync_ui()
        canvas.focus_force();app.update()
        for key,attr in [('s','solo'),('m','muted')]:
            canvas.event_generate(f'<KeyPress-{key}>');app.update()
            assert all(getattr(t,attr) for t in app.project.tracks[:2])
            canvas.event_generate(f'<KeyPress-{key.upper()}>');app.update()
            assert not any(getattr(t,attr) for t in app.project.tracks[:2])
        saves=[];app.save=lambda:saves.append(True)
        # Existing command binding holds the original callable; test Control
        # protection through an extra observable binding on the same toplevel.
        app.bind('<Control-s>',lambda e:saves.append(True))
        canvas.event_generate('<Control-s>');app.update()
        assert saves and not app.track.solo
        entries=[]
        def collect(w):
            if isinstance(w,ttk.Entry):entries.append(w)
            for c in w.winfo_children():collect(c)
        collect(app)
        entry=next(w for w in entries if str(w.cget('textvariable'))==str(app.name_var))
        entry.focus_force();app.update();entry.icursor('end')
        old=entry.get()
        for key in ('s','m'):entry.event_generate(f'<KeyPress-{key}>')
        app.update()
        assert entry.get()==old+'sm' and not app.track.solo and not app.track.muted
    finally:
        app.stop();app.release_output();app.destroy()


def test_drum_editor_editing_preview_and_roundtrip(tmp_path):
    from ui.main_window import MainWindow
    from test_core import Capture
    from services.project_io import load
    from midi import smf
    app=MainWindow()
    try:
        app.output=Capture();app.project.ui['selected']=9
        app.sync_ui();app.update()
        before=[(t.channel,t.msb,t.lsb,t.program) for t in app.project.tracks]
        app.view_var.set('Drum Editor');app.view_change();app.update()
        r=app.roll
        assert r.drum_mode and r.KEY==210 and r.ROW==24
        assert app.roll.winfo_ismapped() and not app.overview.winfo_ismapped()
        assert before==[(t.channel,t.msb,t.lsb,t.program) for t in app.project.tracks]
        labels=[r.keys.itemcget(i,'text') for i in r.keys.find_withtag('drum_label')]
        assert '036  Bass Drum 1' in labels and '042  Closed Hi-Hat' in labels
        def event(pitch,tick):
            return NS(x=r.KEY+tick*r.SCALE-r.canvas.canvasx(0),
                      y=r.TOP+r.pitch_row(pitch)*r.ROW+5-r.canvas.canvasy(0),state=0)
        # Single-click insertion; a subsequent double-click adds no duplicate.
        e=event(36,0);r.down(e);r.up(e);r.double(e)
        assert len(app.track.notes)==1 and app.track.notes[0].pitch==36
        assert app.output.messages[-1].type=='note_on'
        assert app.output.messages[-1].channel==9
        r.app.project.ui['grid']='1/16T'
        e=event(42,160);r.down(e);r.up(e)
        assert [(n.start,n.duration) for n in app.track.notes]==[(0,240),(160,160)]
        r.down(event(36,20));r.motion(event(38,260));r.up(NS())
        note=app.track.notes[0]
        assert note.pitch==38 and note.start==320
        r.vel_drag=True;r.vel_motion(NS(y=40));r.vel_up(NS())
        assert note.velocity==97
        # A numeric lane outside GM is still editable and never drops data.
        r.canvas.yview_moveto(.3);app.update()
        e=event(0,960);r.down(e);r.up(e)
        assert any(n.pitch==0 for n in app.track.notes)
        r.key_down(NS(y=event(0,0).y));r.key_up()
        assert any(m.type=='note_on' and m.note==0 for m in app.output.messages)
        app.path=tmp_path/'drums.juno.json';app.save()
        restored=load(app.path)
        assert restored.ui['view']=='Drum Editor' and restored.ui['drum_yview']>0
        assert restored.tracks[9].notes==app.track.notes
        smf.save(app.project,tmp_path/'drums.mid')
        imported,_=smf.load(tmp_path/'drums.mid')
        expected=sorted((n.start,n.pitch,n.duration,n.velocity) for n in app.track.notes)
        assert sorted((n.start,n.pitch,n.duration,n.velocity) for n in imported.tracks[9].notes)==expected
        # Same notes remain editable in the piano layout; view switches keep data.
        app.view_var.set('Piano Roll');app.view_change();app.update()
        assert not r.drum_mode and r.KEY==62 and r.ROW==16
        assert sorted((n.start,n.pitch,n.duration,n.velocity) for n in app.track.notes)==expected
        app.view_var.set('Drum Editor');app.view_change();app.update()
        assert r.canvas.yview()[0]>0
        r.delete();assert not any(n.pitch==0 for n in app.track.notes)
        app.undo();assert any(n.pitch==0 for n in app.track.notes)
        app.redo();assert not any(n.pitch==0 for n in app.track.notes)
    finally:
        app.stop();app.release_output();app.destroy()


def test_drum_real_click_zoom_follow_and_group_edit():
    from ui.main_window import MainWindow
    from models.project import Note
    from test_core import Capture
    app=MainWindow()
    try:
        app.output=Capture();app.project.ui['selected']=9;app.sync_ui();app.update()
        app.view_var.set('Drum Editor');app.view_change();app.update();r=app.roll
        # Actual Tk click goes through the common editor's bindings.
        x=r.KEY+5;y=r.TOP+r.pitch_row(36)*r.ROW+5
        r.canvas.event_generate('<ButtonPress-1>',x=x,y=y)
        r.canvas.event_generate('<ButtonRelease-1>',x=x,y=y);app.update()
        assert len(app.track.notes)==1
        n=app.track.notes[0]
        app.track.notes.append(Note(480,42,240));r.redraw()
        r.selected={note.id for note in app.track.notes}
        r.down(NS(x=x,y=y,state=0));r.motion(NS(x=x+24,y=y+24,state=0));r.up(NS())
        assert [(note.start,note.pitch) for note in app.track.notes]==[(240,37),(720,43)]
        r.zoom(horizontal=1.25,vertical=1.25);app.update()
        assert r.ROW==30 and r.KEY==210
        app.track.notes.append(Note(80000,81,240));r.redraw()
        app.player.cursor=lambda:70000;app.player.playing=True
        app.draw_cursors(70000);app.update()
        assert r.canvas.xview()[0]>0
        app.player.playing=False
        r.canvas.yview_moveto(.2);app.update()
        before=(r.canvas.xview(),r.canvas.yview())
        app.mute_button.invoke();app.update()
        assert r.canvas.xview()==pytest.approx(before[0],abs=.001)
        assert r.canvas.yview()==pytest.approx(before[1],abs=.001)
    finally:
        app.player.playing=False
        app.stop();app.release_output();app.destroy()
