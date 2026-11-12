import os
import sys
from types import SimpleNamespace as NS
import pytest
from models.project import Note
from services.controllers import cc_events,put_cc
from services.meter import MeterMap
from ui.cc_lane import musical_position,position_tick


def test_positions_use_musical_beats_including_triplets_and_meter_changes():
    meter=MeterMap([[0,3,4],[5760,6,8]])
    for tick in (0,160,320,960,2880,5760,6000,7520):
        assert position_tick(meter,musical_position(meter,tick))==tick
    assert musical_position(meter,2880)=='2|1'
    assert position_tick(meter,'3|2.5')==6480
    with pytest.raises(ValueError):position_tick(meter,'0|1')


requires_gui=pytest.mark.skipif(sys.platform!='darwin' and not os.environ.get('DISPLAY'),reason='GUI display unavailable')


@requires_gui
def test_pedal_draw_uses_note_timeline_and_one_undo(tmp_path):
    from ui.main_window import MainWindow
    from services.project_io import load
    app=MainWindow()
    try:
        app.track.notes=[Note(0,60,960),Note(960,64,960)]
        app.sync_ui();app.update();app.cc_editor();app.update()
        r=app.roll;lane=r.cc_lane
        assert lane.winfo_ismapped() and r.canvas.winfo_ismapped()
        assert not r.velocity.winfo_ismapped()
        r.canvas.yview_moveto(.4)
        before=app.project.data()['tracks'][0]['notes'];history=len(app.history.past)
        x1=round(lane.screen_x(240));x2=round(lane.screen_x(1680));y=70
        lane.canvas.event_generate('<ButtonPress-1>',x=x1,y=y)
        lane.canvas.event_generate('<B1-Motion>',x=x2,y=y)
        lane.canvas.event_generate('<ButtonRelease-1>',x=x2,y=y);app.update()
        assert [(t,v) for _,t,v in cc_events(app.track,64)]==[(240,127),(1680,0)]
        assert app.project.data()['tracks'][0]['notes']==before
        assert len(app.history.past)==history+1
        texts=[lane.canvas.itemcget(i,'text') for i in lane.canvas.find_withtag('cc_ruler')]
        assert '1|1' in texts and '2|1' in texts
        r.zoom(horizontal=2);app.update();r.xview('moveto',.05);app.update()
        assert lane.screen_x(960)==pytest.approx(r.KEY+960*r.SCALE-r.canvas.canvasx(0))
        app.undo();assert not cc_events(app.track,64)
        app.redo();assert len(cc_events(app.track,64))==2
        app.path=tmp_path/'lane.juno.json';app.save()
        assert load(app.path).ui['cc_visible']
    finally:
        app.stop();app.release_output();app.destroy()


@requires_gui
def test_real_shift_list_selection_bulk_value_delete_and_undo():
    from ui.main_window import MainWindow
    app=MainWindow()
    try:
        app.track.notes=[Note(0,60,960)]
        for tick,value in [(0,127),(960,0),(1920,127),(2880,0)]:put_cc(app.track,tick,64,value)
        put_cc(app.track,0,7,85)
        app.sync_ui();app.update();app.roll.selected={app.track.notes[0].id}
        app.cc_editor();lane=app.roll.cc_lane;lane.list_visible.set(True);lane.toggle_list();app.update()
        children=lane.table.get_children()
        for index,state in [(0,0),(2,1)]:
            x,y,w,h=lane.table.bbox(children[index])
            lane.table.event_generate('<ButtonPress-1>',x=x+20,y=y+h//2,state=state)
            lane.table.event_generate('<ButtonRelease-1>',x=x+20,y=y+h//2,state=state);app.update()
        assert len(lane.selected)==3
        lane.value.set('64');lane.set_values()
        assert [v for _,_,v in cc_events(app.track,64)]==[64,64,64,0]
        app.undo();app.update();lane=app.roll.cc_lane
        assert [v for _,_,v in cc_events(app.track,64)]==[127,0,127,0]
        lane.table.selection_set(lane.table.get_children()[:3]);lane.table_select()
        lane.table.focus_force();app.update();lane.table.event_generate('<Delete>');app.update()
        assert [(t,v) for _,t,v in cc_events(app.track,64)]==[(2880,0)]
        assert len(app.track.notes)==1 and cc_events(app.track,7)[0][2]==85
        app.undo();assert len(cc_events(app.track,64))==4
    finally:
        app.stop();app.release_output();app.destroy()


@requires_gui
def test_wheel_on_both_scrollbars_and_cc_is_vertical_unless_shift():
    from ui.main_window import MainWindow
    app=MainWindow()
    try:
        app.track.notes=[Note(80000,60,240)];app.sync_ui();app.update();app.cc_editor();app.update()
        r=app.roll
        for widget in (r.canvas,r.keys,r.ruler,r.velocity,r.hbar,r.vbar,r.cc_lane.canvas):
            r.xview('moveto',.1);r.canvas.yview_moveto(.3);app.update()
            x=r.canvas.canvasx(0);y=r.canvas.canvasy(0)
            widget.event_generate('<MouseWheel>',delta=-3);app.update()
            assert r.canvas.canvasx(0)==x and r.canvas.canvasy(0)>y
            y=r.canvas.canvasy(0)
            widget.event_generate('<Shift-MouseWheel>',delta=-3);app.update()
            assert r.canvas.canvasx(0)>x and r.canvas.canvasy(0)==y
            x=r.canvas.canvasx(0)
            widget.event_generate('<Control-MouseWheel>',delta=-3);app.update()
            assert r.canvas.canvasx(0)==x and r.canvas.canvasy(0)==y
    finally:
        app.stop();app.release_output();app.destroy()


@requires_gui
def test_bulk_musical_move_keeps_spacing_and_cancel_restores_points():
    from ui.main_window import MainWindow
    app=MainWindow()
    try:
        for tick,value in [(240,127),(960,0)]:put_cc(app.track,tick,64,value)
        app.update();app.cc_editor();app.update();lane=app.roll.cc_lane
        lane.selected={i for i,_,_ in lane.events()};lane.position.set('2|1');lane.move_selection()
        assert [(t,v) for _,t,v in lane.events()]==[(3840,127),(4560,0)]
        app.undo();app.update();assert [(t,v) for _,t,v in lane.events()]==[(240,127),(960,0)]
        lane.down(NS(x=lane.screen_x(240),y=lane.y(127),state=0))
        lane.motion(NS(x=lane.screen_x(480),y=lane.y(127),state=0))
        assert lane.events()[0][1]==480
        lane.cancel()
        assert [(t,v) for _,t,v in lane.events()]==[(240,127),(960,0)]
    finally:
        app.stop();app.release_output();app.destroy()
