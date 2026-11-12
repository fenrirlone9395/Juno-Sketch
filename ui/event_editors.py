"""Modal MIDI event editors; edits remain one-step undoable in the main project."""
import tkinter as tk
from tkinter import ttk
from copy import deepcopy
import mido
from services.controllers import CC_NAMES, cc_events, put_cc, sustain
from services.sysex import parse_hex, format_hex
from services.meter import MeterMap


class CcEditor(tk.Toplevel):
    def __init__(self,app):
        super().__init__(app);self.app=app;self.track=app.track
        self.title(f'CC — {self.track.name}');self.geometry('740x580');self.minsize(620,500)
        notes=[n for n in self.track.notes if n.id in app.roll.selected]
        start=min((n.start for n in notes),default=app.playhead)
        meter=MeterMap(app.project.signatures)
        end=max((n.start+n.duration for n in notes),default=meter.bar_start(meter.position(start)[0]+1))
        self.control=tk.StringVar(value='64 Sustain');self.tick=tk.StringVar(value=str(start))
        self.value=tk.StringVar(value='127');self.end=tk.StringVar(value=str(end))
        row=ttk.Frame(self,padding=8);row.pack(fill='x')
        ttk.Label(row,text='CC').pack(side='left')
        box=ttk.Combobox(row,textvariable=self.control,values=[f'{i} {CC_NAMES.get(i,"")}' for i in range(128) if i not in (0,32)],width=22)
        box.pack(side='left');box.bind('<<ComboboxSelected>>',lambda e:self.refresh())
        ttk.Button(row,text='表示',command=lambda:app.guarded(self.refresh)).pack(side='left',padx=4)
        ttk.Label(row,text='Bank Selectはトラック設定で編集').pack(side='left',padx=8)
        self.canvas=tk.Canvas(self,height=152,bg='#20252d',highlightthickness=0)
        self.canvas.pack(fill='x',padx=8);self.canvas.bind('<Configure>',lambda e:self.draw())
        self.canvas.bind('<Button-1>',self.plot_down);self.canvas.bind('<B1-Motion>',self.plot_motion)
        self.canvas.bind('<ButtonRelease-1>',self.plot_up)
        self.table=ttk.Treeview(self,columns=('tick','value'),show='headings',selectmode='browse',height=8)
        self.table.heading('tick',text='Tick');self.table.heading('value',text='Value (0–127)')
        self.table.pack(fill='both',expand=True,padx=8,pady=6)
        self.table.bind('<<TreeviewSelect>>',self.select)
        row=ttk.Frame(self,padding=8);row.pack(fill='x')
        for label,var in [('Tick',self.tick),('Value',self.value)]:
            ttk.Label(row,text=label).pack(side='left')
            ttk.Entry(row,textvariable=var,width=9).pack(side='left',padx=4)
        for label,func in [('追加／同時刻を置換',self.put),('選択を更新',self.update_event),('削除',self.delete)]:
            ttk.Button(row,text=label,command=lambda f=func:app.guarded(f)).pack(side='left',padx=3)
        row=ttk.Frame(self,padding=8);row.pack(fill='x')
        ttk.Label(row,text='ペダル範囲：上のTick → 終了Tick').pack(side='left')
        ttk.Entry(row,textvariable=self.end,width=9).pack(side='left',padx=4)
        ttk.Button(row,text='Sustain ON → OFF',command=lambda:app.guarded(self.pedal)).pack(side='left')
        ttk.Button(row,text='範囲をOFF',command=lambda:app.guarded(lambda:self.pedal(False))).pack(side='left',padx=4)
        ttk.Label(self,text='グラフ：クリックで追加、点をドラッグで移動。横軸はtick、縦軸は0〜127。\n編集中は停止します。再生して確認してください。',padding=8).pack(anchor='w')
        self.drag=None;self.refresh();self.transient(app);self.grab_set()
        self.protocol('WM_DELETE_WINDOW',self.close)
    def cc(self):
        value=int(self.control.get().split()[0])
        if not 0<=value<=127 or value in (0,32):raise ValueError('CCは0／32以外の0〜127です')
        return value
    def select(self,event=None):
        if self.table.selection():
            index=int(self.table.selection()[0]);tick,data=self.track.events[index]
            self.tick.set(tick);self.value.set(data['value'])
    def refresh(self):
        cc=self.cc();self.table.delete(*self.table.get_children())
        for index,tick,value in cc_events(self.track,cc):self.table.insert('', 'end',iid=str(index),values=(tick,value))
        self.draw()
    def draw(self):
        c=self.canvas;c.delete('all');self.points=[]
        try:events=sorted(cc_events(self.track,self.cc()),key=lambda e:e[1])
        except (ValueError,IndexError):return
        self.extent=max(7680,max((t for _,t,_ in events),default=0)+960,
                        max((n.start+n.duration for n in self.track.notes),default=0))
        self.plot_width=max(1,c.winfo_width()-65)
        c.create_text(4,8,text='127',fill='white',anchor='nw');c.create_text(8,128,text='0',fill='white')
        c.create_line(40,12,40,125,fill='#80909f');c.create_line(40,125,40+self.plot_width,125,fill='#80909f')
        for i in range(5):
            x=40+i*self.plot_width/4;c.create_text(x,136,text=str(round(i*self.extent/4)),fill='#acb8c9')
        previous=None
        for index,tick,value in events:
            x=40+tick/self.extent*self.plot_width;y=125-value/127*110
            if previous:c.create_line(previous[0],previous[1],x,previous[1],x,y,fill='#65b9c1')
            c.create_oval(x-4,y-4,x+4,y+4,fill='#f2b961',outline='')
            self.points.append((index,x,y));previous=(x,y)
    def coordinates(self,e):
        tick=max(0,round((e.x-40)/self.plot_width*self.extent))
        return self.app.roll.snap(tick),max(0,min(127,round((125-e.y)/110*127)))
    def plot_down(self,e):
        def action():
            if e.x<40 or e.y>125:return
            self.cc()
            found=next((i for i,x,y in self.points if abs(x-e.x)<8 and abs(y-e.y)<8),None)
            if found is None:
                tick,value=self.coordinates(e);self.tick.set(tick);self.value.set(value);self.put();return
            self.drag=(deepcopy(self.app.project),found,self.extent)
        self.app.guarded(action)
    def plot_motion(self,e):
        if not self.drag:return
        before,index,extent=self.drag
        tick,value=self.coordinates(e)
        self.track.events=deepcopy(before.tracks[self.app.project.ui['selected']].events)
        self.track.events.pop(index);put_cc(self.track,tick,self.cc(),value)
        self.tick.set(tick);self.value.set(value);self.refresh()
        self.extent=extent
    def plot_up(self,e=None):
        if self.drag:
            before,_,_=self.drag;self.drag=None
            if before.data()!=self.app.project.data():self.app.history.push(before);self.app.changed()
    def commit(self,edit):
        before=deepcopy(self.track.events)
        edit()
        after=deepcopy(self.track.events);self.track.events=before
        if before!=after:self.app.checkpoint();self.track.events=after;self.app.changed()
        self.refresh();self.app.overview.sync_mixer()
    def put(self):self.commit(lambda:put_cc(self.track,int(self.tick.get()),self.cc(),int(self.value.get())))
    def update_event(self):
        if not self.table.selection():return
        index=int(self.table.selection()[0]);tick=int(self.tick.get());value=int(self.value.get());cc=self.cc()
        # Validate first so an error cannot remove the previous event.
        test=deepcopy(self.track);put_cc(test,tick,cc,value)
        self.commit(lambda:(self.track.events.pop(index),put_cc(self.track,tick,cc,value)))
    def delete(self):
        if self.table.selection():
            index=int(self.table.selection()[0]);self.commit(lambda:self.track.events.pop(index))
    def pedal(self,on=True):
        self.control.set('64 Sustain')
        self.commit(lambda:sustain(self.track,int(self.tick.get()),int(self.end.get()),on))
    def close(self):
        self.plot_up();self.destroy()


class SysexEditor(tk.Toplevel):
    def __init__(self,app):
        super().__init__(app);self.app=app;self.title('SysEx Editor');self.geometry('760x540')
        self.tick=tk.StringVar(value=str(app.playhead));self.label=tk.StringVar(value='SysEx')
        self.table=ttk.Treeview(self,columns=('tick','name','size'),show='headings',selectmode='browse',height=7)
        for col,title in [('tick','Tick'),('name','名前'),('size','Bytes')]:self.table.heading(col,text=title)
        self.table.pack(fill='both',expand=True,padx=8,pady=8);self.table.bind('<<TreeviewSelect>>',self.select)
        row=ttk.Frame(self,padding=8);row.pack(fill='x')
        for text,var in [('Tick',self.tick),('名前',self.label)]:
            ttk.Label(row,text=text).pack(side='left');ttk.Entry(row,textvariable=var,width=18).pack(side='left',padx=5)
        ttk.Label(self,text='HEX：2桁ずつ空白区切り。F0／F7は両方付けるか両方省略。',padding=8).pack(anchor='w')
        self.hex=tk.Text(self,height=7,font=('TkFixedFont',12),wrap='word');self.hex.pack(fill='both',expand=True,padx=8)
        self.feedback=tk.StringVar();ttk.Label(self,textvariable=self.feedback,padding=8).pack(anchor='w')
        row=ttk.Frame(self,padding=8);row.pack(fill='x')
        for text,func in [('検証・整形',self.check),('追加',self.add),('選択を更新',self.update_event),('削除',self.delete),('今すぐ送信',self.send)]:
            ttk.Button(row,text=text,command=lambda f=func:app.guarded(f)).pack(side='left',padx=3)
        self.send_button=row.winfo_children()[-1]
        if app.project.ui['output']!='JUNO-DS':self.send_button.state(['disabled'])
        ttk.Label(self,text='送信はJUNO-DS出力のみ。再生時は配置tickで送信し、途中再生で過去のSysExは送りません。\n汎用HEX編集です。機種固有のアドレス／チェックサムは自動補完しません。',padding=8).pack(anchor='w')
        self.refresh();self.transient(app);self.grab_set()
    def refresh(self):
        self.table.delete(*self.table.get_children())
        for i,e in enumerate(self.app.project.sysex):self.table.insert('','end',iid=str(i),values=(e['tick'],e['label'],len(e['data'])+2))
    def select(self,event=None):
        if self.table.selection():
            e=self.app.project.sysex[int(self.table.selection()[0])]
            self.tick.set(e['tick']);self.label.set(e['label']);self.hex.delete('1.0','end');self.hex.insert('1.0',format_hex(e['data']))
    def check(self):
        data=parse_hex(self.hex.get('1.0','end'));self.hex.delete('1.0','end');self.hex.insert('1.0',format_hex(data))
        self.feedback.set(f'有効：{len(data)+2} bytes（F0／F7含む）');return data
    def entry(self):
        tick=int(self.tick.get())
        if tick<0:raise ValueError('tickは0以上です')
        return dict(tick=tick,label=self.label.get(),data=self.check())
    def add(self):
        event=self.entry();self.app.checkpoint();self.app.project.sysex.append(event);self.finish()
    def update_event(self):
        if self.table.selection():
            index=int(self.table.selection()[0]);event=self.entry();self.app.checkpoint()
            self.app.project.sysex[index]=event;self.finish()
    def delete(self):
        if self.table.selection():
            self.app.checkpoint();self.app.project.sysex.pop(int(self.table.selection()[0]));self.finish()
    def finish(self):
        self.app.project.sysex.sort(key=lambda e:e['tick']);self.app.changed();self.refresh()
    def send(self):
        if self.app.project.ui['output']!='JUNO-DS':raise ValueError('JUNO-DS出力を選んでください')
        self.app.ensure_output().send(mido.Message('sysex',data=self.check()))
        self.feedback.set('送信しました')
