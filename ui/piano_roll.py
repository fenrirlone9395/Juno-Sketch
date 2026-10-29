import tkinter as tk
from tkinter import ttk
from copy import deepcopy
from models.project import Note, PPQ, GRIDS
from services.meter import MeterMap
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
        self.preview_pitch=None
        self.key_held=False
        self._wheel_remainder={'x':0.0,'y':0.0}
        toolbar=ttk.Frame(self,padding=(2,2));toolbar.grid(row=0,column=0,sticky='ew')
        ttk.Label(toolbar,text='時間').pack(side='left')
        ttk.Button(toolbar,text='−',width=3,command=lambda:self.zoom(horizontal=1/1.25)).pack(side='left')
        ttk.Button(toolbar,text='+',width=3,command=lambda:self.zoom(horizontal=1.25)).pack(side='left')
        self.x_zoom_label=ttk.Label(toolbar,width=5);self.x_zoom_label.pack(side='left',padx=3)
        ttk.Label(toolbar,text='鍵盤').pack(side='left',padx=(8,0))
        ttk.Button(toolbar,text='−',width=3,command=lambda:self.zoom(vertical=1/1.25)).pack(side='left')
        ttk.Button(toolbar,text='+',width=3,command=lambda:self.zoom(vertical=1.25)).pack(side='left')
        self.y_zoom_label=ttk.Label(toolbar,width=5);self.y_zoom_label.pack(side='left',padx=3)
        ttk.Button(toolbar,text='100%',width=5,command=lambda:self.zoom(reset=True)).pack(side='left',padx=5)
        self.horizontal_wheel=tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar,text='ホイール横',variable=self.horizontal_wheel,
                        command=self.wheel_mode_changed).pack(side='left',padx=8)
        self.canvas=tk.Canvas(self,bg='#20252d',highlightthickness=0,xscrollincrement=1,yscrollincrement=1)
        self.velocity=tk.Canvas(self,bg='#191e26',height=110,highlightthickness=0)
        self.ruler=tk.Canvas(self,bg='#20252d',height=28,highlightthickness=0)
        self.keys=tk.Canvas(self.canvas,bg='#d2d6dc',width=self.KEY,highlightthickness=0)
        self.keys.place(x=0,y=0,width=self.KEY,relheight=1)
        self.keys.bind('<Button-1>',self.key_down)
        self.keys.bind('<B1-Motion>',self.key_motion)
        self.keys.bind('<ButtonRelease-1>',self.key_up)
        self.keys.bind('<FocusOut>',self.key_up)
        self.keys.bind('<Unmap>',self.key_up)
        self.ruler.bind('<Button-1>',lambda e:self.app.set_playhead(max(0,round((self.canvas.canvasx(e.x)-self.KEY)/self.SCALE))))
        self.vbar=tk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        self.hbar=tk.Scrollbar(self,orient='horizontal',command=self.xview)
        self.canvas.configure(xscrollcommand=self.xchanged,yscrollcommand=self.ychanged)
        self.ruler.grid(row=1,column=0,sticky='ew')
        self.canvas.grid(row=2,column=0,sticky='nsew')
        self.vbar.grid(row=2,column=1,sticky='ns')
        self.velocity.grid(row=3,column=0,sticky='ew')
        self.hbar.grid(row=4,column=0,sticky='ew')
        self.rowconfigure(2,weight=1)
        self.columnconfigure(0,weight=1)
        for seq,func in [('<Button-1>',self.down),('<B1-Motion>',self.motion),('<ButtonRelease-1>',self.up),('<Double-Button-1>',self.double),('<Button-2>',self.context),('<Button-3>',self.context)]:
            self.canvas.bind(seq,func)
        for widget in (self.canvas,self.keys,self.ruler,self.velocity,self.hbar):
            horizontal=widget in (self.ruler,self.velocity,self.hbar)
            widget.bind('<MouseWheel>',lambda e,h=horizontal:self.wheel(e,horizontal=h))
            # Aqua sends native horizontal trackpad gestures as Shift-MouseWheel.
            widget.bind('<Shift-MouseWheel>',lambda e:self.wheel(e,horizontal=True))
            widget.bind('<Control-MouseWheel>',lambda e:self.wheel_zoom(e,vertical=False))
            widget.bind('<Control-Shift-MouseWheel>',lambda e:self.wheel_zoom(e,vertical=True))
            widget.bind('<Button-4>',lambda e,h=horizontal:self.wheel(e,horizontal=h))
            widget.bind('<Button-5>',lambda e,h=horizontal:self.wheel(e,horizontal=h))
            widget.bind('<Shift-Button-4>',lambda e:self.wheel(e,horizontal=True))
            widget.bind('<Shift-Button-5>',lambda e:self.wheel(e,horizontal=True))
        self.velocity.bind('<Button-1>',self.vel_down)
        self.velocity.bind('<B1-Motion>',self.vel_motion)
        self.velocity.bind('<ButtonRelease-1>',self.vel_up)
        self.sync_zoom()
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
            self.keys.create_rectangle(0,y,self.KEY,y+self.ROW,fill='#f2b961' if pitch==self.preview_pitch else ('#363b45' if black else '#d2d6dc'),outline='#555c67')
            if pitch%12==0:
                self.keys.create_text(30,y+8,text=f'C{pitch//12-1}',fill='#222')
    def draw_ruler(self):
        self.ruler.delete('all')
        offset=self.canvas.canvasx(0)
        width=max(self.ruler.winfo_width(),1)
        meter=MeterMap(self.app.project.signatures)
        start=max(0,int((offset-self.KEY)/self.SCALE))
        end=start+int(width/self.SCALE)+PPQ
        for tick,bar,beat,n,d in meter.beats(start,end):
            x=self.KEY+tick*self.SCALE-offset
            if beat==1 or PPQ*4/d*self.SCALE>=40:
                self.ruler.create_text(x+3,14,text=f'{bar}|{beat}',anchor='w',fill='#e3e8f0')
            self.ruler.create_line(x,22,x,28,fill='#8b97a6')
        self.ruler.create_rectangle(0,0,self.KEY,28,fill='#20252d',outline='')
    def xview(self,*args):
        self.canvas.xview(*args)
        self.velocity.xview_moveto(self.canvas.xview()[0])
    def sync_zoom(self):
        self.SCALE=0.10*self.app.project.ui.get('zoom_x',1.0)
        self.ROW=max(8,min(40,round(16*self.app.project.ui.get('zoom_y',1.0))))
        self.x_zoom_label.configure(text=f'{self.SCALE/0.10:.0%}')
        self.y_zoom_label.configure(text=f'{self.ROW/16:.0%}')
        self.horizontal_wheel.set(self.app.project.ui.get('wheel_horizontal',False))
    def wheel_mode_changed(self):
        self.app.project.ui['wheel_horizontal']=self.horizontal_wheel.get()
        self.app.changed()
    def zoom(self,horizontal=1.0,vertical=1.0,reset=False,anchor=None):
        if self.drag or getattr(self,'vel_drag',False):return
        c=self.canvas
        screen_x,screen_y=anchor or (self.KEY+max(1,c.winfo_width()-self.KEY)/2,c.winfo_height()/2)
        anchor_tick=(c.canvasx(screen_x)-self.KEY)/self.SCALE
        anchor_row=(c.canvasy(screen_y)-self.TOP)/self.ROW
        x=1.0 if reset else max(0.25,min(4.0,self.SCALE/0.10*horizontal))
        row=16 if reset else max(8,min(40,round(self.ROW*vertical)))
        self.app.project.ui.update(zoom_x=x,zoom_y=row/16)
        self.sync_zoom();self.redraw()
        region=[float(value) for value in c.cget('scrollregion').split()]
        c.xview_moveto(max(0,(self.KEY+anchor_tick*self.SCALE-screen_x)/region[2]))
        c.yview_moveto(max(0,(self.TOP+anchor_row*self.ROW-screen_y)/region[3]))
        self.velocity.xview_moveto(c.xview()[0])
        self.draw_keys();self.draw_ruler()
        self.app.changed()
        if hasattr(self.app,'draw_cursors'):
            self.app.draw_cursors(self.app.player.cursor() if self.app.player.playing else self.app.playhead)
    def wheel_delta(self,event):
        number=getattr(event,'num',None)
        if number in (4,5):return 1 if number==4 else -1
        delta=getattr(event,'delta',0)
        return delta/120 if self.tk.call('tk','windowingsystem')=='win32' else delta
    def wheel(self,e,horizontal=False):
        horizontal=horizontal or bool(getattr(e,'state',0)&1) or self.horizontal_wheel.get()
        axis='x' if horizontal else 'y'
        self._wheel_remainder[axis]+=max(-200,min(200,-self.wheel_delta(e)*12))
        pixels=int(self._wheel_remainder[axis])
        self._wheel_remainder[axis]-=pixels
        if pixels:
            if horizontal:self.xview('scroll',pixels,'units')
            else:self.canvas.yview_scroll(pixels,'units')
        return 'break'
    def wheel_zoom(self,event,vertical=False):
        direction=self.wheel_delta(event)
        if not direction:return 'break'
        factor=1.25 if direction>0 else 1/1.25
        # event.x/y may refer to the fixed keys/ruler instead of the note canvas.
        widget=event.widget
        anchor=(widget.winfo_rootx()+event.x-self.canvas.winfo_rootx(),
                widget.winfo_rooty()+event.y-self.canvas.winfo_rooty())
        self.zoom(horizontal=1 if vertical else factor,vertical=factor if vertical else 1,anchor=anchor)
        return 'break'
    def key_pitch(self,event):
        y=self.canvas.canvasy(event.y)
        if not self.TOP<=y<self.TOP+128*self.ROW:return None
        return 127-int((y-self.TOP)//self.ROW)
    def key_down(self,event):
        self.keys.focus_set()
        pitch=self.key_pitch(event)
        if pitch is not None:
            self.app.audition(pitch,self.track.velocity,hold=True)
            self.preview_pitch=pitch;self.key_held=True;self.draw_keys()
        return 'break'
    def key_motion(self,event):
        if self.key_held:
            pitch=self.key_pitch(event)
            if pitch is not None and pitch!=self.preview_pitch:self.key_down(event)
        return 'break'
    def key_up(self,event=None):
        if self.key_held:
            self.key_held=False;self.preview_pitch=None
            self.app.end_audition();self.draw_keys()
        return 'break'
    def snap(self,t):
        t=max(0,round(t))
        if self.app.project.ui['mode']=='Grid':
            step=GRIDS[self.app.project.ui['grid']]
            return MeterMap(self.app.project.signatures).snap(t,step)
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
        meter=MeterMap(self.app.project.signatures)
        end_tick=meter.extent(project_end(self.app.project),self.app.project.ui.get('bars',8))
        width=self.KEY+end_tick*self.SCALE
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
        previous_grid_x=-100
        for tick in meter.grid_ticks(end_tick,step):
            x=self.KEY+tick*self.SCALE
            if x-previous_grid_x<4:continue
            previous_grid_x=x
            c.create_line(x,self.TOP,x,height,fill='#434b59')
        for tick,bar,beat,n,d in meter.beats(0,end_tick):
            x=self.KEY+tick*self.SCALE
            c.create_line(x,self.TOP,x,height,fill='#727b8a' if beat==1 else '#505b6b',tags='meter_line')
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
            self.app.audition(n.pitch,n.velocity)
            self.drag=dict(kind='resize' if self.coords(n)[2]-x<=7 else 'move',audition=0,x=x,y=y,before=deepcopy(self.app.project),original={k.id:deepcopy(k) for k in self.track.notes if k.id in self.selected},pitch=n.pitch)
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
