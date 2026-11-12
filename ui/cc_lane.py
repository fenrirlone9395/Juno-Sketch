"""Inline controller lane with the piano roll's scale, scroll and meter."""
from copy import deepcopy
import tkinter as tk
from tkinter import ttk
from models.project import GRIDS
from services.controllers import CC_NAMES, cc_events, put_cc, sustain
from services.meter import MeterMap


def musical_position(meter,tick):
    bar,beat,remainder,_,_=meter.position(tick)
    fraction=beat+remainder/meter.segment(tick).beat_ticks
    return f'{bar}|{fraction:.6f}'.rstrip('0').rstrip('.')


def position_tick(meter,text):
    try:
        bar,beat=text.split('|');bar=int(bar);beat=float(beat)
        start=meter.bar_start(bar);segment=meter.segment(start)
        if not 1<=beat<segment.numerator+1:raise ValueError()
        tick=start+round((beat-1)*segment.beat_ticks)
        if tick>=meter.bar_start(bar+1):raise ValueError()
        return tick
    except (ValueError,OverflowError):
        raise ValueError('位置は小節|拍です。例：2|1、2|2.5') from None


class CcLane(ttk.Frame):
    TOP=28
    BOTTOM=132

    def __init__(self,parent,roll):
        super().__init__(parent);self.roll=roll;self.app=roll.app
        self.selected=set();self.drag=None;self.current_tick=0;self._track=None;self._refreshing=False
        self.control=tk.StringVar(value='64 Sustain');self.value=tk.StringVar(value='127')
        self.position=tk.StringVar(value='1|1');self.list_visible=tk.BooleanVar(value=False)
        top=ttk.Frame(self);top.pack(fill='x')
        ttk.Label(top,text='CC').pack(side='left',padx=4)
        self.box=ttk.Combobox(top,textvariable=self.control,state='readonly',width=17,
            values=[f'{i} {CC_NAMES.get(i,"")}' for i in range(128) if i not in (0,32)])
        self.box.pack(side='left');self.box.bind('<<ComboboxSelected>>',self.control_change)
        ttk.Button(top,text='選択ノートにペダル',command=lambda:self.app.guarded(self.notes_pedal)).pack(side='left',padx=4)
        ttk.Button(top,text='選択CCを削除',command=self.delete).pack(side='left',padx=4)
        ttk.Checkbutton(top,text='イベント一覧',variable=self.list_visible,command=self.toggle_list).pack(side='left',padx=4)
        ttk.Button(top,text='Velocityへ',command=self.hide).pack(side='right',padx=4)
        self.canvas=tk.Canvas(self,height=150,bg='#191e26',highlightthickness=0)
        self.canvas.pack(fill='x');self.canvas.bind('<Configure>',lambda e:self.draw())
        self.canvas.bind('<Button-1>',self.down);self.canvas.bind('<B1-Motion>',self.motion)
        self.canvas.bind('<ButtonRelease-1>',self.up)
        self.canvas.bind('<Button-3>',self.context)
        self.canvas.bind('<Button-2>',self.context)
        self.canvas.bind('<Escape>',self.cancel)
        roll.bind_wheel(self.canvas)
        self.list_frame=ttk.Frame(self)
        self.table=ttk.Treeview(self.list_frame,columns=('position','value'),show='headings',height=4,selectmode='extended')
        self.table.heading('position',text='小節 | 拍');self.table.heading('value',text='Value')
        self.table.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(self.list_frame,orient='vertical',command=self.table.yview)
        scroll.pack(side='right',fill='y');self.table.configure(yscrollcommand=scroll.set)
        self.table.bind('<<TreeviewSelect>>',self.table_select)
        bottom=ttk.Frame(self);bottom.pack(fill='x')
        ttk.Label(bottom,text='位置').pack(side='left',padx=4)
        ttk.Entry(bottom,textvariable=self.position,width=9).pack(side='left')
        ttk.Label(bottom,text='値').pack(side='left',padx=4)
        ttk.Spinbox(bottom,textvariable=self.value,from_=0,to=127,width=4).pack(side='left')
        ttk.Button(bottom,text='追加',command=lambda:self.app.guarded(self.add)).pack(side='left',padx=3)
        ttk.Button(bottom,text='値を一括適用',command=lambda:self.app.guarded(self.set_values)).pack(side='left',padx=3)
        ttk.Button(bottom,text='選択位置を移動',command=lambda:self.app.guarded(self.move_selection)).pack(side='left',padx=3)
        self.selection_label=ttk.Label(bottom);self.selection_label.pack(side='left',padx=5)
        self.hint=ttk.Label(self,text='Sustain：横ドラッグでON → OFF。点をドラッグで編集。Shiftクリック／囲みで複数選択。')
        self.hint.pack(anchor='w',padx=4)
        self.toggle_list();self.refresh()
    @property
    def track(self):return self.app.track
    def cc(self):return int(self.control.get().split()[0])
    def events(self):return cc_events(self.track,self.cc())
    def show(self):
        self.app.project.ui['cc_visible']=True
        self.roll.velocity.grid_remove();self.grid(row=3,column=0,sticky='ew')
        self.refresh();self.canvas.focus_set()
    def hide(self):
        self.cancel();self.app.project.ui['cc_visible']=False
        self.grid_remove();self.roll.velocity.grid();self.app.changed()
    def control_change(self,event=None):
        self.cancel();self.selected.clear();self.app.project.ui['cc_control']=self.cc()
        self.refresh();self.app.changed()
    def toggle_list(self):
        if self.list_visible.get():self.list_frame.pack(fill='x',after=self.canvas)
        else:self.list_frame.pack_forget()
    def focused(self):
        return self.app.focus_get() in (self.canvas,self.table)
    def table_select(self,event=None):
        if self._refreshing:return
        self.selected={int(i) for i in self.table.selection()}
        self.update_fields();self.draw()
    def update_fields(self):
        if self.selected:
            tick,data=self.track.events[min(self.selected)]
            self.position.set(musical_position(MeterMap(self.app.project.signatures),tick));self.value.set(data['value'])
        self.selection_label.configure(text=f'選択 {len(self.selected)}')
    def refresh(self):
        control=self.app.project.ui.get('cc_control',64)
        if self.cc()!=control:
            self.control.set(f'{control} {CC_NAMES.get(control,"")}');self.selected.clear()
        if self._track is not self.track:
            self.selected.clear();self.drag=None;self._track=self.track
        self.selected.intersection_update(i for i,_,_ in self.events())
        self._refreshing=True
        self.table.delete(*self.table.get_children())
        meter=MeterMap(self.app.project.signatures)
        for i,tick,value in self.events():
            self.table.insert('','end',iid=str(i),values=(musical_position(meter,tick),value))
        self.table.selection_set(tuple(str(i) for i in self.selected))
        self._refreshing=False
        self.update_fields();self.draw()
    def draw(self):
        if not self.canvas.winfo_exists():return
        c=self.canvas;c.delete('all');self.points=[]
        key=self.roll.KEY;scale=self.roll.SCALE;offset=self.roll.canvas.canvasx(0)
        width=c.winfo_width();meter=MeterMap(self.app.project.signatures)
        start=max(0,int((offset-key)/scale));end=start+int(max(1,width)/scale)+960
        previous_x=-100
        for tick in meter.grid_ticks(end,GRIDS[self.app.project.ui['grid']]):
            x=key+tick*scale-offset
            if x<key:continue
            if x-previous_x<4:continue
            c.create_line(x,self.TOP,x,self.BOTTOM,fill='#303946');previous_x=x
        for tick,bar,beat,_,_ in meter.beats(start,end):
            x=key+tick*scale-offset
            if x<key:continue
            c.create_line(x,20,x,self.BOTTOM,fill='#596575' if beat==1 else '#394453')
            if beat==1 or meter.segment(tick).beat_ticks*scale>=40:
                c.create_text(x+3,12,text=f'{bar}|{beat}',anchor='w',fill='#c6d0de',tags='cc_ruler')
        # Draw a step function, including the state carried into the visible area.
        previous=(key, self.y(0));events=sorted(self.events(),key=lambda e:e[1])
        for i,tick,value in events:
            x=key+tick*scale-offset;y=self.y(value)
            if x<key:previous=(key,y);continue
            if self.cc()==64 and previous[1]<=self.y(64):
                c.create_rectangle(previous[0],self.TOP,min(x,width),self.BOTTOM,fill='#284b44',outline='')
            c.create_line(previous[0],previous[1],x,previous[1],x,y,fill='#69bac0')
            c.create_oval(x-4,y-4,x+4,y+4,fill='#f2b961' if i in self.selected else '#73c5ce',outline='',tags='cc_point')
            self.points.append((i,x,y));previous=(x,y)
            if x>width:break
        if self.cc()==64 and previous[1]<=self.y(64):
            c.create_rectangle(previous[0],self.TOP,width,self.BOTTOM,fill='#284b44',outline='')
        c.create_line(previous[0],previous[1],width,previous[1],fill='#69bac0')
        c.tag_raise('cc_point')
        c.create_rectangle(0,0,key,150,fill='#191e26',outline='')
        c.create_text(5,12,text=f'CC {self.cc()}',anchor='w',fill='#c6d0de')
        c.create_text(5,self.TOP,text='ON' if self.cc()==64 else '127',anchor='w',fill='#c6d0de')
        c.create_text(5,self.BOTTOM,text='OFF' if self.cc()==64 else '0',anchor='w',fill='#c6d0de')
        if self.drag and self.drag['kind'] in ('pedal','box'):
            x1=self.screen_x(self.drag['start']);x2=self.screen_x(self.drag['end'])
            c.create_rectangle(x1,self.TOP,x2,self.BOTTOM,outline='#f2b961',dash=(3,3))
        self.cursor(self.current_tick)
    def cursor(self,tick):
        self.current_tick=tick;self.canvas.delete('playhead')
        x=self.screen_x(tick)
        if x>=self.roll.KEY:self.canvas.create_line(x,0,x,150,fill='#ff6b73',width=2,tags='playhead')
    def screen_x(self,tick):return self.roll.KEY+tick*self.roll.SCALE-self.roll.canvas.canvasx(0)
    def y(self,value):return self.BOTTOM-value/127*(self.BOTTOM-self.TOP)
    def tick_at(self,x):
        return self.roll.snap((self.roll.canvas.canvasx(x)-self.roll.KEY)/self.roll.SCALE)
    def value_at(self,y):
        value=max(0,min(127,round((self.BOTTOM-y)/(self.BOTTOM-self.TOP)*127)))
        return (127 if value>=64 else 0) if self.cc()==64 else value
    def down(self,event):
        self.canvas.focus_set()
        if event.x<self.roll.KEY:return 'break'
        if event.y<self.TOP:self.app.set_playhead(self.tick_at(event.x));return 'break'
        hit=next((i for i,x,y in reversed(self.points) if abs(x-event.x)<=8 and abs(y-event.y)<=9),None)
        shift=bool(event.state&1)
        if hit is not None:
            if shift:
                if hit in self.selected:self.selected.remove(hit)
                else:self.selected.add(hit)
            elif hit not in self.selected:self.selected={hit}
            if hit not in self.selected:self.refresh();return 'break'
            self.drag=dict(kind='move',before=deepcopy(self.app.project),
                           originals=deepcopy(self.track.events),start=self.tick_at(event.x),y=event.y)
        elif shift:
            self.drag=dict(kind='box',start=self.tick_at(event.x),end=self.tick_at(event.x),base=set(self.selected))
        elif self.cc()==64:
            self.selected.clear();self.drag=dict(kind='pedal',start=self.tick_at(event.x),end=self.tick_at(event.x))
        else:
            tick=self.tick_at(event.x);value=self.value_at(event.y)
            self.commit(lambda:put_cc(self.track,tick,self.cc(),value))
        self.refresh();return 'break'
    def motion(self,event):
        if not self.drag:return 'break'
        d=self.drag
        if d['kind'] in ('pedal','box'):
            d['end']=self.tick_at(event.x)
            if d['kind']=='box':
                low,high=sorted((d['start'],d['end']))
                self.selected=d['base']|{i for i,t,_ in self.events() if low<=t<=high}
        else:
            delta=self.tick_at(event.x)-d['start']
            old=d['originals'];anchor=min(old[i][0] for i in self.selected)
            delta=max(-anchor,delta);dv=self.value_at(event.y)-self.value_at(d['y'])
            values=[old[i][1]['value'] for i in self.selected]
            dv=max(-min(values),min(127-max(values),dv))
            self.track.events=deepcopy(old)
            for i in self.selected:
                self.track.events[i][0]=old[i][0]+delta
                self.track.events[i][1]['value']=old[i][1]['value']+dv
        self.draw();return 'break'
    def up(self,event=None):
        if not self.drag:return 'break'
        d=self.drag;self.drag=None
        if d['kind']=='pedal':
            start,end=sorted((d['start'],d['end']))
            if start==end:end=start+GRIDS[self.app.project.ui['grid']]
            self.commit(lambda:sustain(self.track,start,end))
        elif d['kind']=='move':
            if d['before'].data()!=self.app.project.data():
                self.app.history.push(d['before']);self.app.changed()
            self.track.events.sort(key=lambda e:e[0]);self.selected.clear();self.roll.redraw()
        self.refresh();return 'break'
    def cancel(self,event=None):
        if self.drag and self.drag['kind']=='move':self.track.events=self.drag['originals']
        self.drag=None;self.draw()
        return 'break'
    def commit(self,edit):
        self.app.stop()
        before=deepcopy(self.track.events)
        try:edit();after=deepcopy(self.track.events)
        except Exception:
            self.track.events=before;raise
        self.track.events=before
        if before!=after:
            self.app.checkpoint();self.track.events=after;self.app.changed()
        self.selected.clear();self.roll.redraw();self.app.overview.sync_mixer();self.refresh()
    def add(self):
        tick=position_tick(MeterMap(self.app.project.signatures),self.position.get())
        self.commit(lambda:put_cc(self.track,tick,self.cc(),int(self.value.get())))
    def set_values(self):
        if not self.selected:return
        value=int(self.value.get())
        if not 0<=value<=127:raise ValueError('値は0〜127です')
        indices=set(self.selected)
        def edit():
            for i in indices:self.track.events[i][1]['value']=value
        self.commit(edit)
        self.selected=indices;self.refresh()
    def move_selection(self):
        if not self.selected:return
        target=position_tick(MeterMap(self.app.project.signatures),self.position.get())
        indices=set(self.selected);delta=target-min(self.track.events[i][0] for i in indices)
        def edit():
            for i in indices:self.track.events[i][0]+=delta
            self.track.events.sort(key=lambda e:e[0])
        self.commit(edit)
    def delete(self,event=None):
        indices=set(self.selected)
        if indices:self.commit(lambda:setattr(self.track,'events',[e for i,e in enumerate(self.track.events) if i not in indices]))
        return 'break'
    def select_all(self):
        self.selected={i for i,_,_ in self.events()};self.refresh()
    def context(self,event):
        hit=next((i for i,x,y in self.points if abs(x-event.x)<=8 and abs(y-event.y)<=9),None)
        if hit is not None:
            if hit not in self.selected:self.selected={hit}
            self.delete()
        return 'break'
    def notes_pedal(self):
        notes=[n for n in self.track.notes if n.id in self.roll.selected]
        if not notes:raise ValueError('ピアノロールでノートを選択してください')
        self.control.set('64 Sustain');self.app.project.ui['cc_control']=64
        self.commit(lambda:sustain(self.track,min(n.start for n in notes),max(n.start+n.duration for n in notes)))
