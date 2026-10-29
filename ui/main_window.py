import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import mido
from models.project import Project, GRIDS, PPQ
from services.undo import History
from services import project_io
from midi import smf
from midi.player import Player
from midi.internal_preview import InternalPreviewOutput
from midi.juno_ds import JunoDsOutput
from ui.piano_roll import PianoRoll
from ui.overview import TrackOverview
from ui.track_colors import track_color

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('JUNO Sketch • v0.1.1')
        self.geometry('1240x820')
        self.minsize(940,620)
        self.project=Project();self.history=History();self.player=Player()
        self.output=None;self.path=None;self.dirty=False;self.playhead=0;self.was_playing=False
        self.audition_job=None;self.audition_note=None;self.audition_generation=0
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.build_menu()
        self.build_toolbar()
        body=ttk.Frame(self);body.pack(fill='both',expand=True)
        left=ttk.Frame(body,width=215,padding=8);left.pack(side='left',fill='y')
        ttk.Label(left,text='MIDI TRACKS',font=('',12,'bold')).pack(anchor='w')
        self.list=tk.Listbox(left,exportselection=False,height=16,width=25)
        self.list.pack(fill='x',pady=8)
        self.list.bind('<<ListboxSelect>>',self.select_track)
        self.fields={}
        for key,label,low,high in [('channel','Channel',1,16),('msb','Bank MSB',0,127),('lsb','Bank LSB',0,127),('program','Program (1–128)',1,128),('velocity','Default Velocity',1,127)]:
            row=ttk.Frame(left);row.pack(fill='x',pady=3)
            ttk.Label(row,text=label).pack(side='left')
            v=tk.StringVar();self.fields[key]=v
            ttk.Spinbox(row,textvariable=v,from_=low,to=high,width=5).pack(side='right')
        ttk.Button(left,text='設定を適用・音色送信',command=self.apply_track).pack(fill='x',pady=10)
        ttk.Label(left,text='空白をダブルクリック：作成\nノート中央：移動\n右端：長さ変更\nShiftクリック／囲む：複数選択\n右クリック／Delete：削除\n下のバー：Velocity\nルーラー：再生開始位置\nホイール：上下移動\nShift＋ホイール：左右移動',justify='left').pack(anchor='w',pady=8)
        self.editor_body=ttk.Frame(body)
        self.editor_body.pack(side='left',fill='both',expand=True)
        self.roll=PianoRoll(self.editor_body,self)
        self.overview=TrackOverview(self.editor_body,self)
        self.roll.pack(fill='both',expand=True)
        self.status=tk.StringVar(value='Ready • 4/4 • PPQ 960')
        ttk.Label(self,textvariable=self.status,anchor='w',padding=6).pack(fill='x')
        for key in ('<Delete>','<BackSpace>'):
            self.bind(key,self.delete_key)
        self.bind('<space>',self.space)
        for modifier in ('Command','Control'):
            for key,func in [('z',self.undo),('Z',self.redo),('s',self.save),('o',self.open),('n',self.new)]:
                self.bind(f'<{modifier}-{key}>',lambda e,f=func:self.shortcut(f))
            self.bind(f'<{modifier}-Shift-z>',lambda e:self.shortcut(self.redo))
        self.sync_ui();self.after(25,self.poll)
    @property
    def track(self): return self.project.tracks[self.project.ui['selected']]
    def guarded(self,func):
        try: return func()
        except Exception as exc:
            messagebox.showerror('JUNO Sketch',str(exc),parent=self)
    def report_callback_exception(self,typ,value,tb):
        import traceback,logging
        logging.error('UI error',exc_info=(typ,value,tb))
        messagebox.showerror('JUNO Sketch',str(value),parent=self)
    def build_menu(self):
        bar=tk.Menu(self);self.config(menu=bar)
        file=tk.Menu(bar,tearoff=False);bar.add_cascade(label='File',menu=file)
        for label,func in [('New',self.new),('Open Project…',self.open),('Save Project',self.save),('Save Project As…',lambda:self.save(True)),('Import MIDI…',self.import_midi),('Export MIDI…',self.export_midi)]:
            file.add_command(label=label,command=lambda f=func:self.guarded(f))
        edit=tk.Menu(bar,tearoff=False);bar.add_cascade(label='Edit',menu=edit)
        edit.add_command(label='Undo',command=self.undo);edit.add_command(label='Redo',command=self.redo)
        edit.add_command(label='Select All Notes',command=self.select_all)
        helpmenu=tk.Menu(bar,tearoff=False);bar.add_cascade(label='Help',menu=helpmenu)
        helpmenu.add_command(label='操作方法',command=lambda:messagebox.showinfo('JUNO Sketch','空白をダブルクリックしてノート作成。\nGrid / Slip と三連符は上部で切替。\nMIDI Channelは1–16、Programは1–128で表示。\n内部音源はGMの近似音色です。JUNOの音色とは異なります。\nJUNOはPerformanceの16パートで受信する設定にしてください。'))
    def build_toolbar(self):
        top=ttk.Frame(self,padding=8);top.pack(fill='x')
        ttk.Button(top,text='▶ / ■ Space',command=lambda:self.guarded(self.toggle)).pack(side='left')
        ttk.Button(top,text='|◀',width=3,command=lambda:self.set_playhead(0)).pack(side='left',padx=4)
        self.bpm=tk.StringVar(value='120')
        ttk.Label(top,text='BPM').pack(side='left')
        entry=ttk.Entry(top,textvariable=self.bpm,width=6);entry.pack(side='left',padx=4)
        entry.bind('<Return>',lambda e:self.guarded(self.apply_bpm()))
        ttk.Button(top,text='適用',width=4,command=lambda:self.guarded(self.apply_bpm)).pack(side='left')
        self.mode=tk.StringVar(value='Grid');self.grid_var=tk.StringVar(value='1/16')
        for v,values,width in [(self.mode,['Grid','Slip'],6),(self.grid_var,list(GRIDS),7)]:
            box=ttk.Combobox(top,textvariable=v,values=values,state='readonly',width=width);box.pack(side='left',padx=5)
            box.bind('<<ComboboxSelected>>',self.grid_change)
        self.output_var=tk.StringVar(value='Internal Preview');self.port=tk.StringVar()
        out=ttk.Combobox(top,textvariable=self.output_var,values=['Internal Preview','JUNO-DS'],state='readonly',width=15)
        out.pack(side='left',padx=5);out.bind('<<ComboboxSelected>>',self.output_change)
        self.portbox=ttk.Combobox(top,textvariable=self.port,state='readonly',width=20);self.portbox.pack(side='left')
        self.portbox.bind('<<ComboboxSelected>>',self.output_change)
        ttk.Button(top,text='ポート更新',command=lambda:self.guarded(self.refresh_ports)).pack(side='left',padx=4)
        views=ttk.Frame(self,padding=(8,0,8,6));views.pack(fill='x')
        ttk.Label(views,text='View').pack(side='left')
        self.view_var=tk.StringVar(value='Piano Roll')
        view=ttk.Combobox(views,textvariable=self.view_var,values=['Piano Roll','All Tracks'],state='readonly',width=13)
        view.pack(side='left',padx=6);view.bind('<<ComboboxSelected>>',self.view_change)
        self.ghost_var=tk.BooleanVar(value=True)
        self.ghost_button=ttk.Checkbutton(views,text='他トラックをレイヤー表示',variable=self.ghost_var,command=self.layer_change)
        self.ghost_button.pack(side='left',padx=10)
        self.follow_var=tk.BooleanVar(value=True)
        ttk.Checkbutton(views,text='全体表示で再生位置に追従',variable=self.follow_var,command=self.follow_change).pack(side='left',padx=10)
        ttk.Label(views,text='All Tracks: 16トラック表示 / ダブルクリックで編集').pack(side='left',padx=8)
    def sync_ui(self):
        self.list.delete(0,'end')
        for i,t in enumerate(self.project.tracks):self.list.insert('end',f'{i+1:02}  {t.name}  [Ch {t.channel+1}]')
        for i in range(16):
            self.list.itemconfigure(i,foreground=track_color(i),background='#20252d',selectbackground='#434b59',selectforeground=track_color(i))
        index=self.project.ui['selected'];self.list.selection_set(index)
        self.fields['channel'].set(self.track.channel+1)
        for k in ('msb','lsb','velocity'):self.fields[k].set(getattr(self.track,k))
        self.fields['program'].set(self.track.program+1)
        self.bpm.set(f'{self.project.bpm:g}')
        self.mode.set(self.project.ui['mode']);self.grid_var.set(self.project.ui['grid'])
        self.output_var.set(self.project.ui['output']);self.port.set(self.project.ui.get('port',''))
        self.view_var.set(self.project.ui.get('view','Piano Roll'))
        self.ghost_var.set(self.project.ui.get('show_ghosts',True))
        self.follow_var.set(self.project.ui.get('follow_playhead',True))
        self.roll.selected.clear();self.roll.drag=None;self.roll.vel_drag=False
        self.show_view()
        self.roll.redraw();self.overview.redraw()
        self.draw_cursors(self.player.cursor() if self.player.playing else self.playhead)
    def show_view(self):
        overview=self.project.ui.get('view','Piano Roll')=='All Tracks'
        if overview:
            self.roll.pack_forget();self.overview.pack(fill='both',expand=True)
            self.ghost_button.state(['disabled'])
        else:
            self.overview.pack_forget();self.roll.pack(fill='both',expand=True)
            self.ghost_button.state(['!disabled'])
    def view_change(self,e=None):
        self.project.ui['view']=self.view_var.get()
        self.roll.drag=None;self.roll.vel_drag=False
        self.show_view()
        self.roll.redraw();self.overview.redraw()
        self.draw_cursors(self.player.cursor() if self.player.playing else self.playhead)
        self.changed()
        self.focus_set()
    def layer_change(self):
        self.project.ui['show_ghosts']=self.ghost_var.get()
        self.roll.redraw();self.changed()
        self.draw_cursors(self.player.cursor() if self.player.playing else self.playhead)
    def follow_change(self):
        self.project.ui['follow_playhead']=self.follow_var.get();self.changed()
    def draw_cursors(self,tick):
        self.roll.cursor(tick)
        self.overview.cursor(tick,follow=self.player.playing and self.project.ui.get('view')=='All Tracks' and self.project.ui.get('follow_playhead',True))
    def select_track(self,e):
        if self.list.curselection():
            self.project.ui['selected']=self.list.curselection()[0]
            self.sync_ui()
    def checkpoint(self): self.history.push(self.project)
    def changed(self):
        self.dirty=True
        self.title(f'JUNO Sketch • {self.path.name if self.path else "Untitled"} *')
    def apply_track(self):
        def action():
            vals={k:int(v.get()) for k,v in self.fields.items()}
            vals['channel']-=1;vals['program']-=1
            if not (0<=vals['channel']<16 and 0<=vals['program']<128 and all(0<=vals[k]<=127 for k in ('msb','lsb')) and 1<=vals['velocity']<=127):
                raise ValueError('設定値が範囲外です')
            self.stop();self.checkpoint()
            for k,v in vals.items():setattr(self.track,k,v)
            self.changed();self.sync_ui()
            self.ensure_output().setup(self.track)
        self.guarded(action)
    def apply_bpm(self):
        bpm=float(self.bpm.get())
        if not 20<=bpm<=400:raise ValueError('BPMは20〜400です')
        self.stop()
        if bpm!=self.project.bpm:
            self.checkpoint();self.project.bpm=bpm;self.project.tempos=[];self.changed()
    def grid_change(self,e):
        self.project.ui.update(mode=self.mode.get(),grid=self.grid_var.get());self.changed();self.roll.redraw()
    def refresh_ports(self):
        ports=JunoDsOutput.ports();self.portbox['values']=ports
        self.status.set('MIDIポート: '+(', '.join(ports) or 'なし'))
    def output_change(self,e=None):
        def action():
            self.stop();self.release_output()
            self.project.ui.update(output=self.output_var.get(),port=self.port.get());self.changed()
        self.guarded(action)
    def ensure_output(self):
        if self.output is None:
            self.output=InternalPreviewOutput() if self.project.ui['output']=='Internal Preview' else JunoDsOutput(self.project.ui.get('port',''))
        return self.output
    def end_audition(self):
        if self.audition_job:
            self.after_cancel(self.audition_job);self.audition_job=None
        if self.audition_note and self.output:
            ch,pitch=self.audition_note
            self.audition_note=None
            self.output.send(mido.Message('note_off',channel=ch,note=pitch))
    def audition(self,pitch,velocity):
        if self.player.playing:return
        try:
            self.end_audition();out=self.ensure_output();out.setup(self.track)
            out.send(mido.Message('note_on',channel=self.track.channel,note=pitch,velocity=velocity))
            self.audition_note=(self.track.channel,pitch)
            self.audition_job=self.after(170,lambda:self.guarded(self.end_audition))
        except Exception as exc:
            self.status.set(str(exc))
    def release_output(self):
        self.end_audition()
        if self.output:
            output=self.output;self.output=None;output.close()
    def toggle(self):
        if self.player.playing:self.stop()
        else:
            self.apply_bpm();self.end_audition()
            self.player.start(self.project,self.ensure_output(),self.playhead)
    def stop(self):
        if self.player.playing:self.playhead=int(self.player.cursor())
        self.player.stop()
        self.player.position=self.playhead
        self.end_audition()
        if self.output:self.output.panic()
    def set_playhead(self,tick):
        self.stop();self.playhead=tick;self.draw_cursors(tick)
    def poll(self):
        if self.player.playing:
            cursor=self.player.cursor();self.draw_cursors(cursor)
            beat=int(cursor)//PPQ;self.status.set(f'Playing  {beat//4+1}|{beat%4+1}   tick {int(cursor)%PPQ}')
        if self.was_playing and not self.player.playing:
            self.playhead=int(self.player.position);self.draw_cursors(self.playhead)
            self.status.set('Stopped')
        self.was_playing=self.player.playing
        while not self.player.errors.empty():
            self.status.set('出力エラー: '+self.player.errors.get())
        self.after(25,self.poll)
    def text_focus(self):
        return isinstance(self.focus_get(),(tk.Entry,ttk.Entry,ttk.Spinbox,ttk.Combobox))
    def delete_key(self,e):
        if not self.text_focus() and self.project.ui.get('view')!='All Tracks':self.roll.delete();return 'break'
    def space(self,e):
        if not self.text_focus():self.guarded(self.toggle);return 'break'
    def shortcut(self,func):
        self.guarded(func);return 'break'
    def select_all(self):
        if self.project.ui.get('view')=='All Tracks':return
        self.roll.selected={n.id for n in self.track.notes};self.roll.redraw()
    def undo(self):
        self.stop();self.release_output();self.project=self.history.undo(self.project);self.changed();self.sync_ui()
    def redo(self):
        self.stop();self.release_output();self.project=self.history.redo(self.project);self.changed();self.sync_ui()
    def confirm_discard(self):
        if not self.dirty:return True
        choice=messagebox.askyesnocancel('未保存の変更','変更を保存しますか？',parent=self)
        if choice is None:return False
        return bool(self.save()) if choice else True
    def replace(self,p,path=None):
        self.stop();self.release_output();self.project=p;self.path=path;self.history=History();self.playhead=0;self.dirty=False
        self.title(f'JUNO Sketch • {path.name if path else "Untitled"}')
        self.sync_ui()
        self.restore_view()
    def new(self):
        if self.confirm_discard():self.replace(Project())
    def open(self):
        if not self.confirm_discard():return
        path=filedialog.askopenfilename(filetypes=[('JUNO Sketch','*.juno.json'),('JSON','*.json')])
        if path:self.replace(project_io.load(path),Path(path))
    def save(self,save_as=False):
        path=self.path
        if not path or save_as:
            result=filedialog.asksaveasfilename(defaultextension='.juno.json',filetypes=[('JUNO Sketch','*.juno.json')])
            if not result:return False
            path=Path(result)
        self.capture_view()
        project_io.save(self.project,path);self.path=path;self.dirty=False
        self.title(f'JUNO Sketch • {path.name}');self.status.set('プロジェクトを保存しました')
        return True
    def import_midi(self):
        if not self.confirm_discard():return
        path=filedialog.askopenfilename(filetypes=[('MIDI','*.mid *.midi')])
        if path:
            p,warnings=smf.load(path);self.replace(p);self.changed()
            if warnings:messagebox.showwarning('MIDI Import','\n'.join(warnings))
    def export_midi(self):
        path=filedialog.asksaveasfilename(defaultextension='.mid',filetypes=[('MIDI Type 1','*.mid')])
        if path:smf.save(self.project,path);self.status.set('SMF Type 1を保存しました')
    def capture_view(self):
        self.project.ui.update(geometry=self.geometry(),xview=self.roll.canvas.xview()[0],yview=self.roll.canvas.yview()[0],overview_xview=self.overview.canvas.xview()[0])
    def restore_view(self):
        ui=self.project.ui
        if 'geometry' in ui:self.geometry(ui['geometry'])
        self.roll.canvas.xview_moveto(ui.get('xview',0));self.roll.velocity.xview_moveto(ui.get('xview',0))
        self.roll.canvas.yview_moveto(ui.get('yview',0.43))
        self.overview.canvas.xview_moveto(ui.get('overview_xview',0))
    def close(self):
        if self.confirm_discard():
            self.stop();self.release_output();self.destroy()
