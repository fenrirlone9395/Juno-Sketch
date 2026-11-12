"""Modal MIDI event editors; edits remain one-step undoable in the main project."""
import tkinter as tk
from tkinter import ttk
import mido
from services.sysex import parse_hex, format_hex


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
