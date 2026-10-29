"""Editor interaction tests without an OS display; exercise actual handlers."""
from types import SimpleNamespace as NS
from models.project import Project, Note
from services.undo import History
from ui.piano_roll import PianoRoll

class Canvas:
    def canvasx(self,x):return x
    def canvasy(self,y):return y
    def focus_set(self):pass
    def create_rectangle(self,*a,**k):pass

class App:
    def __init__(self):
        self.project=Project();self.history=History();self.heard=[]
    @property
    def track(self):return self.project.tracks[0]
    def checkpoint(self):self.history.push(self.project)
    def changed(self):pass
    def audition(self,p,v):self.heard.append(p)

def editor():
    # Construct without Tcl; no drawing methods are substituted in production.
    r=PianoRoll.__new__(PianoRoll)
    r.app=App();r.canvas=Canvas();r.velocity=Canvas();r.selected=set();r.drag=None
    r.redraw=lambda:None;r.draw_velocity=lambda:None
    return r

def event(x,y,state=0):return NS(x=x,y=y,state=state)

def test_create_move_resize_delete_undo():
    r=editor();y=r.TOP+(127-60)*r.ROW+5
    r.double(event(r.KEY+3,y))
    assert len(r.track.notes)==1
    n=r.track.notes[0];assert (n.start,n.pitch,n.duration)==(0,60,240)
    r.down(event(r.KEY+4,y));r.motion(event(r.KEY+28,y-16));r.up(event(0,0))
    assert (n.start,n.pitch)==(240,61)
    x=r.coords(n)[2]-1;y=r.coords(n)[1]+4
    r.down(event(x,y));r.motion(event(x+24,y));r.up(event(0,0))
    assert n.duration==480
    r.delete();assert not r.track.notes
    r.app.project=r.app.history.undo(r.app.project)
    assert r.track.notes[0].duration==480
    assert 61 in r.app.heard

def test_slip_triplets_velocity_and_multi_selection():
    r=editor();r.app.project.ui['grid']='1/16T'
    y=r.TOP+(127-60)*r.ROW+5
    r.double(event(r.KEY+16,y));assert r.track.notes[0].start==160
    r.app.project.ui['mode']='Slip';assert r.snap(173)==173
    r.track.notes.append(Note(600,64,160));r.selected={n.id for n in r.track.notes}
    r.vel_drag=True;r.vel_motion(event(0,20))
    assert all(n.velocity==127 for n in r.track.notes)
    r.delete();assert not r.track.notes
