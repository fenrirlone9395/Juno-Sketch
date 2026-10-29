import tkinter as tk
from copy import deepcopy
from models.project import Note, PPQ, GRIDS
from ui.track_colors import track_color, ghost_color, project_end

class PianoRoll(tk.Frame):
    ROW=16
    KEY=62
    TOP=28
    SCALE=0.10
    def __init__(self,parent,app):
        super().__init__(parent)
        self.app=app
        self.selected=set()
        self.drag=None
        self.canvas=tk.Canvas(self,bg='#20252d',highlightthickness=0)
        self.velocity=tk.Canvas(self,bg='#191e26',height=110,highlightthickness=0)
        self.ruler=tk.Canvas(self,bg='#20252d',height=28,highlightthickness=0)
        self.keys=tk.Canvas(self.canvas,bg='#d2d6dc',width=self.KEY,highlightthickness=0)
        self.keys.place(x=0,y=0,width=self.KEY,relheight=1)
        self.ruler.bind('<Button-1>',lambda e:self.app.set_playhead(max(0,round((self.canvas.canvasx(e.x)-self.KEY)/self.SCALE))))
        self.vbar=tk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        self.hbar=tk.Scrollbar(self,orient='horizontal',command=self.xview)
        self.canvas.configure(xscrollcommand=self.xchanged,yscrollcommand=self.ychanged)
        self.ruler.grid(row=0,column=0,sticky='ew')
        self.canvas.grid(row=1,column=0,sticky='nsew')
        self.vbar.grid(row=1,column=1,sticky='ns')
        self.velocity.grid(row=2,column=0,sticky='ew')
        self.hbar.grid(row=3,column=0,sticky='ew')
        self.rowconfigure(1,weight=1)
        self.columnconfigure(0,weight=1)
        for seq,func in [('<Button-1>',self.down),('<B1-Motion>',self.motion),('<ButtonRelease-1>',self.up),('<Double-Button-1>',self.double),('<Button-2>',self.context),('<Button-3>',self.context)]:
            self.canvas.bind(seq,func)
        self.canvas.bind('<MouseWheel>',self.wheel)
        self.velocity.bind('<Button-1>',self.vel_down)
        self.velocity.bind('<B1-Motion>',self.vel_motion)
        self.velocity.bind('<ButtonRelease-1>',self.vel_up)
        self.redraw()
        self.canvas.yview_moveto(0.43)
    @property
    def track(self): return self.app.track
    def xchanged(self,first,last):
        self.hbar.set(first,last)
        self.velocity.xview_moveto(float(first))
        self.draw_ruler()
    def ychanged(self,first,last):
        self.vbar.set(first,last)
        self.draw_keys()
    def draw_keys(self):
        self.keys.delete('all')
        offset=self.canvas.canvasy(0)
        for pitch in range(128):
            y=self.TOP+(127-pitch)*self.ROW-offset
            black=pitch%12 in (1,3,6,8,10)
            self.keys.create_rectangle(0,y,self.KEY,y+self.ROW,fill='#363b45' if black else '#d2d6dc',outline='#555c67')
            if pitch%12==0:
                self.keys.create_text(30,y+8,text=f'C{pitch//12-1}',fill='#222')
    def draw_ruler(self):
        self.ruler.delete('all')
        offset=self.canvas.canvasx(0)
        width=max(self.ruler.winfo_width(),1)
        first=max(0,int((offset-self.KEY)/(PPQ*self.SCALE)))
        last=first+int(width/(PPQ*self.SCALE))+3
        for beat in range(first,last):
            x=self.KEY+beat*PPQ*self.SCALE-offset
            self.ruler.create_text(x+3,14,text=f'{beat//4+1}|{beat%4+1}',anchor='w',fill='#e3e8f0')
            self.ruler.create_line(x,22,x,28,fill='#8b97a6')
        self.ruler.create_rectangle(0,0,self.KEY,28,fill='#20252d',outline='')
    def xview(self,*args):
        self.canvas.xview(*args)
        self.velocity.xview_moveto(self.canvas.xview()[0])
    def wheel(self,e):
        if e.state&1:
            self.xview('scroll',-1 if e.delta>0 else 1,'units')
        else:
            self.canvas.yview_scroll(-1 if e.delta>0 else 1,'units')
    def snap(self,t):
        t=max(0,round(t))
        if self.app.project.ui['mode']=='Grid':
            step=GRIDS[self.app.project.ui['grid']]
            return int((t+step/2)//step*step)
        return t
    def coords(self,n):
        return (self.KEY+n.start*self.SCALE,self.TOP+(127-n.pitch)*self.ROW,
                self.KEY+(n.start+n.duration)*self.SCALE,self.TOP+(128-n.pitch)*self.ROW-1)
    def hit(self,x,y):
        return next((n for n in reversed(self.track.notes) if self.coords(n)[0]<=x<=self.coords(n)[2] and self.coords(n)[1]<=y<=self.coords(n)[3]),None)
    def redraw(self):
        c=self.canvas
        view=c.xview()[0]
        c.delete('all')
        bars=max(self.app.project.ui.get('bars',8),2+project_end(self.app.project)//(4*PPQ))
        width=self.KEY+bars*4*PPQ*self.SCALE
        height=self.TOP+128*self.ROW
        c.configure(scrollregion=(0,0,width,height))
        for pitch in range(128):
            y=self.TOP+(127-pitch)*self.ROW
            black=pitch%12 in (1,3,6,8,10)
            c.create_rectangle(0,y,width,y+self.ROW,fill='#262c35' if black else '#303742',outline='#393f49')
            c.create_rectangle(0,y,self.KEY,y+self.ROW,fill='#363b45' if black else '#d2d6dc',outline='#555c67')
            if pitch%12==0:
                c.create_text(30,y+8,text=f'C{pitch//12-1}',fill='#222')
        step=GRIDS[self.app.project.ui['grid']]
        for tick in range(0,bars*4*PPQ+1,step):
            x=self.KEY+tick*self.SCALE
            c.create_line(x,self.TOP,x,height,fill='#727b8a' if tick%(4*PPQ)==0 else '#434b59')
        active = self.app.project.ui['selected']
        if self.app.project.ui.get('show_ghosts', True):
            for index, track in enumerate(self.app.project.tracks):
                if index == active:
                    continue
                for note in track.notes:
                    c.create_rectangle(*self.coords(note), fill=ghost_color(index),
                                       outline=ghost_color(index), tags=('ghost', f'track_{index}'))
        for n in self.track.notes:
            c.create_rectangle(*self.coords(n),fill='#f2b961' if n.id in self.selected else track_color(active),outline='#f8e0b4' if n.id in self.selected else '#89d4d9',tags=('note',))
        self.velocity.configure(scrollregion=(0,0,width,110))
        self.velocity.xview_moveto(view)
        self.draw_velocity()
        self.draw_ruler();self.draw_keys()
        self.cursor(self.app.playhead)
    def draw_velocity(self):
        v=self.velocity
        v.delete('all')
        v.create_text(8,10,text='Velocity',fill='#acb8c9',anchor='w')
        for n in sorted(self.track.notes,key=lambda n:n.id in self.selected):
            x=self.KEY+n.start*self.SCALE
            v.create_rectangle(x,105-n.velocity/127*85,x+6,105,fill='#f2b961' if n.id in self.selected else '#55b4bb',outline='')
    def cursor(self,tick):
        c=self.canvas
        c.delete('playhead')
        x=self.KEY+tick*self.SCALE
        c.create_line(x,0,x,self.TOP+128*self.ROW,fill='#ff6b73',width=2,tags='playhead')
    def down(self,e):
        self.canvas.focus_set()
        x,y=self.canvas.canvasx(e.x),self.canvas.canvasy(e.y)
        if y<self.TOP:
            self.app.set_playhead(max(0,round((x-self.KEY)/self.SCALE)))
            return
        if x<self.KEY: return
        n=self.hit(x,y)
        shift=bool(e.state&1)
        if n:
            if shift:
                if n.id in self.selected: self.selected.remove(n.id)
                else: self.selected.add(n.id)
            elif n.id not in self.selected: self.selected={n.id}
            if n.id not in self.selected:
                self.redraw(); return
            self.drag=dict(kind='resize' if self.coords(n)[2]-x<=7 else 'move',x=x,y=y,before=deepcopy(self.app.project),original={k.id:deepcopy(k) for k in self.track.notes if k.id in self.selected},pitch=n.pitch)
        else:
            if not shift: self.selected.clear()
            self.drag=dict(kind='box',x=x,y=y,base=set(self.selected))
        self.redraw()
    def motion(self,e):
        if not self.drag: return
        d=self.drag
        x,y=self.canvas.canvasx(e.x),self.canvas.canvasy(e.y)
        if d['kind']=='box':
            x1,x2=sorted((d['x'],x));y1,y2=sorted((d['y'],y))
            self.selected=d['base']|{n.id for n in self.track.notes if self.coords(n)[0]<=x2 and self.coords(n)[2]>=x1 and self.coords(n)[1]<=y2 and self.coords(n)[3]>=y1}
            self.redraw()
            self.canvas.create_rectangle(x1,y1,x2,y2,outline='#f2b961',dash=(3,3))
            return
        originals=d['original']
        delta=round((x-d['x'])/self.SCALE)
        pitch_delta=round((d['y']-y)/self.ROW)
        min_pitch=min(n.pitch for n in originals.values());max_pitch=max(n.pitch for n in originals.values())
        pitch_delta=max(-min_pitch,min(127-max_pitch,pitch_delta))
        anchor=min(n.start for n in originals.values())
        movement=self.snap(anchor+delta)-anchor
        movement=max(-anchor,movement)
        for n in self.track.notes:
            if n.id not in originals: continue
            old=originals[n.id]
            if d['kind']=='move':
                n.start=old.start+movement
                n.pitch=old.pitch+pitch_delta
            else:
                n.duration=max(1,self.snap(old.start+old.duration+delta)-old.start)
        if d['kind']=='move' and d.get('audition')!=pitch_delta:
            d['audition']=pitch_delta
            first=next(iter(originals.values()))
            self.app.audition(first.pitch+pitch_delta,first.velocity)
        self.redraw()
    def up(self,e):
        if not self.drag: return
        d=self.drag;self.drag=None
        if d['kind']!='box' and d['before'].data()!=self.app.project.data():
            self.app.history.push(d['before']);self.app.changed()
        self.redraw()
    def double(self,e):
        x,y=self.canvas.canvasx(e.x),self.canvas.canvasy(e.y)
        if x<self.KEY or y<self.TOP or self.hit(x,y): return
        self.app.checkpoint()
        n=Note(self.snap((x-self.KEY)/self.SCALE),max(0,min(127,127-int((y-self.TOP)//self.ROW))),GRIDS[self.app.project.ui['grid']],self.track.velocity)
        self.track.notes.append(n)
        self.selected={n.id};self.drag=None
        self.app.audition(n.pitch,n.velocity)
        self.app.changed();self.redraw()
    def delete(self):
        if not self.selected: return
        self.app.checkpoint()
        self.track.notes[:]=[n for n in self.track.notes if n.id not in self.selected]
        self.selected.clear();self.app.changed();self.redraw()
    def context(self,e):
        n=self.hit(self.canvas.canvasx(e.x),self.canvas.canvasy(e.y))
        if n:
            self.selected={n.id};self.delete()
    def vel_down(self,e):
        x=self.velocity.canvasx(e.x)
        candidates=[n for n in self.track.notes if abs(self.KEY+n.start*self.SCALE-x)<=8]
        if not candidates: return
        candidates.sort(key=lambda n:(n.id not in self.selected,abs(self.KEY+n.start*self.SCALE-x)))
        n=candidates[0]
        self.app.checkpoint()
        if n.id not in self.selected: self.selected={n.id}
        self.vel_drag=True
        self.vel_motion(e)
    def vel_motion(self,e):
        if not getattr(self,'vel_drag',False): return
        value=max(1,min(127,round((105-e.y)*127/85)))
        for n in self.track.notes:
            if n.id in self.selected: n.velocity=value
        self.app.changed();self.draw_velocity()
    def vel_up(self,e):
        self.vel_drag=False
