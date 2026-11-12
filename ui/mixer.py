"""Compact MIDI CC7/CC10 mixer, embedded in the All Tracks view."""
import tkinter as tk
from tkinter import ttk
from copy import deepcopy
from services.controllers import cc_value
from ui.track_colors import track_color


class MidiMixer(ttk.Frame):
    def __init__(self,parent,app):
        super().__init__(parent);self.app=app;self.updating=True;self.before=None;self.controls=[]
        ttk.Label(self,text='MIDI Mixer • Volume CC7 / Pan CC10（開始時の設定・後続CCで上書き）').pack(anchor='w')
        self.canvas=tk.Canvas(self,height=176,highlightthickness=0,xscrollincrement=1)
        self.canvas.pack(fill='x',expand=True)
        scroll=ttk.Scrollbar(self,orient='horizontal',command=self.canvas.xview);scroll.pack(fill='x')
        self.canvas.configure(xscrollcommand=scroll.set)
        for widget in (self.canvas,scroll):
            for seq in ('<MouseWheel>','<Shift-MouseWheel>','<Button-4>','<Button-5>','<Shift-Button-4>','<Shift-Button-5>'):
                widget.bind(seq,self.wheel)
        frame=ttk.Frame(self.canvas);self.canvas.create_window(0,0,window=frame,anchor='nw')
        for i in range(16):
            strip=ttk.Frame(frame,padding=4);strip.grid(row=0,column=i)
            name=ttk.Label(strip,width=13,foreground=track_color(i));name.pack()
            for cc,label,low,high in [(7,'Volume',127,0),(10,'Pan',0,127)]:
                ttk.Label(strip,text=label).pack()
                scale=tk.Scale(strip,from_=low,to=high,orient='vertical' if cc==7 else 'horizontal',
                    length=65 if cc==7 else 90,width=9,showvalue=True,resolution=1,
                    command=lambda value,index=i,control=cc:self.change(index,control,value))
                scale.pack();scale.bind('<ButtonPress-1>',self.begin,add='+')
                scale.bind('<ButtonRelease-1>',self.end,add='+')
                self.controls.append((i,cc,name,scale))
        frame.update_idletasks();self.canvas.configure(scrollregion=self.canvas.bbox('all'),height=frame.winfo_reqheight())
        self.sync()
    def wheel(self,event):
        if getattr(event,'state',0)&4:return 'break'
        pixels=round(max(-200,min(200,-self.app.roll.wheel_delta(event)*12)))
        if getattr(event,'state',0)&1:self.canvas.xview_scroll(pixels,'units')
        else:self.app.overview.canvas.yview_scroll(pixels,'units')
        return 'break'
    def begin(self,event=None):
        self.before=deepcopy(self.app.project)
    def end(self,event=None):
        if self.before is not None:
            if self.before.data()!=self.app.project.data():self.app.history.push(self.before)
            self.before=None
    def change(self,index,cc,value):
        if self.updating:return
        value=int(float(value))
        if value==cc_value(self.app.project.tracks[index],cc):return
        if self.before is None:self.app.checkpoint()
        self.app.set_mixer_cc(index,cc,value)
    def sync(self):
        self.updating=True
        for index,cc,name,scale in self.controls:
            track=self.app.project.tracks[index]
            name.configure(text=f'{index+1:02} {track.name[:11]}')
            scale.set(cc_value(track,cc))
        # Scale commands are idle callbacks; release suppression after they run.
        self.after_idle(self.ready)
    def ready(self):self.updating=False
