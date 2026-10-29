import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import mido
from models.project import Project, GRIDS, PPQ
from services.undo import History
from services import project_io, patch_names
from services.output_mode import switch_destination
from services.track_state import audible_tracks
from services.meter import MeterMap, set_at_bar, remove_at_bar
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
        self.title('JUNO Sketch • v0.1.8')
        self.geometry('1240x820')
        self.minsize(940,620)
        self.project=Project();self.history=History();self.player=Player()
        self.output=None;self.path=None;self.dirty=False;self.playhead=0;self.was_playing=False
        self.audition_job=None;self.audition_note=None;self.audition_preview=None
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.build_menu()
        self.build_toolbar()
        body=ttk.Frame(self);body.pack(fill='both',expand=True)
        left=ttk.Frame(body,width=215,padding=8);left.pack(side='left',fill='y')
        ttk.Label(left,text='MIDI TRACKS',font=('',12,'bold')).pack(anchor='w')
        list_frame=ttk.Frame(left);list_frame.pack(fill='x',pady=8)
        self.list=tk.Listbox(list_frame,exportselection=False,selectmode='extended',height=14,width=25)
        self.list.pack(side='left',fill='both',expand=True)
        track_scroll=ttk.Scrollbar(list_frame,orient='vertical',command=self.list.yview)
        track_scroll.pack(side='right',fill='y');self.list.configure(yscrollcommand=track_scroll.set)
        self.list.bind('<Button-1>',self.remember_track_click)
        self.list.bind('<<ListboxSelect>>',self.select_track)
        self.selection_status=tk.StringVar()
        ttk.Label(left,textvariable=self.selection_status).pack(anchor='w')
        states=ttk.Frame(left);states.pack(fill='x',pady=2)
        self.solo_var=tk.BooleanVar(value=False);self.mute_var=tk.BooleanVar(value=False)
        self.solo_button=tk.Button(states,text='Solo',width=9,takefocus=False,
                                   command=lambda:self.toggle_play_state('solo'))
        self.mute_button=tk.Button(states,text='Mute',width=9,takefocus=False,
                                   command=lambda:self.toggle_play_state('muted'))
        self.solo_button.pack(side='left');self.mute_button.pack(side='left',padx=12)
        self.name_var=tk.StringVar()
        name_row=ttk.Frame(left);name_row.pack(fill='x',pady=3)
        ttk.Label(name_row,text='Name').pack(side='left')
        name_entry=ttk.Entry(name_row,textvariable=self.name_var,width=18)
        name_entry.pack(side='right')
        name_entry.bind('<Return>',lambda e:self.apply_track())
        self.fields={}
        for key,label,low,high in [('channel','Channel',1,16),('msb','Bank MSB',0,127),('lsb','Bank LSB',0,127),('program','Program (1–128)',1,128),('velocity','Default Velocity',1,127)]:
            row=ttk.Frame(left);row.pack(fill='x',pady=3)
            ttk.Label(row,text=label).pack(side='left')
            v=tk.StringVar();self.fields[key]=v
            ttk.Spinbox(row,textvariable=v,from_=low,to=high,width=5).pack(side='right')
        self.patch_label=tk.StringVar(value='')
        ttk.Label(left,textvariable=self.patch_label,wraplength=205).pack(fill='x',pady=3)
        self.auto_name_var=tk.BooleanVar(value=False)
        ttk.Checkbutton(left,text='音色変更時に名前を追従',variable=self.auto_name_var,
                        command=self.naming_change).pack(anchor='w')
        self.patch_name_button=ttk.Button(left,text='音色名をトラック名へ適用',command=self.apply_patch_name)
        self.patch_name_button.pack(fill='x',pady=3)
        for key in ('msb','lsb','program'):
            self.fields[key].trace_add('write',lambda *args:self.update_patch_label())
        ttk.Button(left,text='設定を適用・音色送信',command=self.apply_track).pack(fill='x',pady=10)
        self.editor_help=tk.StringVar()
        ttk.Label(left,textvariable=self.editor_help,justify='left').pack(anchor='w',pady=8)
        self.editor_body=ttk.Frame(body)
        self.editor_body.pack(side='left',fill='both',expand=True)
        self.roll=PianoRoll(self.editor_body,self)
        self.overview=TrackOverview(self.editor_body,self)
        self.roll.pack(fill='both',expand=True)
        self.status=tk.StringVar(value='Ready • PPQ 960')
        ttk.Label(self,textvariable=self.status,anchor='w',padding=6).pack(side='bottom',fill='x',before=body)
        for key in ('<Delete>','<BackSpace>'):
            self.bind(key,self.delete_key)
        self.install_transport_keys()
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
        helpmenu.add_command(label='操作方法',command=lambda:messagebox.showinfo('JUNO Sketch','Piano Roll: 空白をダブルクリックして作成。\nDrum Editor: 空白をクリック、楽器名を押して試聴。\nShift＋空白ドラッグで範囲選択。\nGrid / Slip と三連符は上部で切替。\nMIDI Channelは1–16、Programは1–128で表示。\n内部音源はGMの近似音色です。JUNOの音色とは異なります。\nJUNOはPerformanceの16パートで受信する設定にしてください。'))
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
        view=ttk.Combobox(views,textvariable=self.view_var,values=['Piano Roll','Drum Editor','All Tracks'],state='readonly',width=13)
        view.pack(side='left',padx=6);view.bind('<<ComboboxSelected>>',self.view_change)
        self.meter_button=ttk.Button(views,text='拍子 4/4…',command=self.meter_dialog)
        self.meter_button.pack(side='left',padx=6)
        self.ghost_var=tk.BooleanVar(value=True)
        self.ghost_button=ttk.Checkbutton(views,text='他トラックをレイヤー表示',variable=self.ghost_var,command=self.layer_change)
        self.ghost_button.pack(side='left',padx=10)
        self.follow_var=tk.BooleanVar(value=True)
        ttk.Checkbutton(views,text='再生位置に追従',variable=self.follow_var,command=self.follow_change).pack(side='left',padx=10)
        self.view_hint=ttk.Label(views,text='All Tracks: ダブルクリックで編集')
        self.view_hint.pack(side='left',padx=8)
    def selected_track_indices(self):
        active=self.project.ui['selected']
        selection=set(self.project.ui.get('track_selection',[active]))
        return sorted(selection) if active in selection else [active]
    def sync_ui(self,clear_notes=True):
        selection=self.selected_track_indices()
        self.project.ui['track_selection']=selection
        anchor=self.list.index('anchor') if self.list.size() else self.project.ui['selected']
        list_view=self.list.yview()[0] if self.list.size() else 0
        self.list.delete(0,'end')
        allowed=audible_tracks(self.project.tracks)
        for i,t in enumerate(self.project.tracks):
            flags=('S' if t.solo else '-')+('M' if t.muted else '-')
            self.list.insert('end',f'{i+1:02} {flags}  {t.name}  [Ch {t.channel+1}]')
        for i in range(16):
            self.list.itemconfigure(i,foreground=track_color(i) if allowed[i] else '#7c8490',background='#20252d',selectbackground='#434b59',selectforeground=track_color(i))
        index=self.project.ui['selected']
        for selected in selection:self.list.selection_set(selected)
        self.list.activate(index);self.list.selection_anchor(anchor)
        self.list.yview_moveto(list_view);self.list.see(index)
        self.selection_status.set(f'選択 {len(selection)} / 編集 {index+1:02}')
        self.patch_name_button.configure(text=f'音色名を適用（選択 {len(selection)}）')
        for attr,var,button in [('solo',self.solo_var,self.solo_button),('muted',self.mute_var,self.mute_button)]:
            values=[getattr(self.project.tracks[i],attr) for i in selection]
            var.set(all(values))
            mixed=any(values) and not all(values)
            label='Solo' if attr=='solo' else 'Mute'
            color='#e9bf55' if attr=='solo' else '#ed8b79'
            button.configure(text=label,
                             relief='sunken' if all(values) else 'ridge' if mixed else 'raised',
                             background=color if all(values) else '#d9d9d9',
                             activebackground=color if all(values) else '#ececec')
        first=MeterMap(self.project.signatures).segments[0]
        self.meter_button.configure(text=f'拍子 {first.numerator}/{first.denominator}…')
        self.name_var.set(self.track.name)
        self.auto_name_var.set(self.track.auto_name)
        self.fields['channel'].set(self.track.channel+1)
        for k in ('msb','lsb','velocity'):self.fields[k].set(getattr(self.track,k))
        self.fields['program'].set(self.track.program+1)
        self.bpm.set(f'{self.project.bpm:g}')
        self.mode.set(self.project.ui['mode']);self.grid_var.set(self.project.ui['grid'])
        self.output_var.set(self.project.ui['output']);self.port.set(self.project.ui.get('port',''))
        self.update_patch_label()
        self.view_var.set(self.project.ui.get('view','Piano Roll'))
        self.ghost_var.set(self.project.ui.get('show_ghosts',True))
        self.follow_var.set(self.project.ui.get('follow_playhead',True))
        layout_changed=self.roll.KEY!=(210 if self.project.ui.get('view')=='Drum Editor' else 62)
        if clear_notes:self.roll.selected.clear()
        self.roll.drag=None;self.roll.vel_drag=False
        self.roll.sync_zoom()
        self.show_view()
        self.roll.redraw();self.overview.redraw()
        if layout_changed:self.restore_editor_view()
        self.draw_cursors(self.player.cursor() if self.player.playing else self.playhead)
    def show_view(self):
        overview=self.project.ui.get('view','Piano Roll')=='All Tracks'
        drum=self.project.ui.get('view')=='Drum Editor'
        self.view_hint.configure(text='GM参考名 / ドラム音色を設定してください' if drum else 'All Tracks: ダブルクリックで編集')
        gesture='クリック：作成 / 楽器名：試聴' if drum else 'ダブルクリック：作成 / 右端：長さ'
        self.editor_help.set(gesture+'\nShiftクリック／囲む：複数選択\n詳しい操作はHelpメニュー')
        if overview:
            self.roll.pack_forget();self.overview.pack(fill='both',expand=True)
            self.ghost_button.state(['disabled'])
        else:
            self.overview.pack_forget();self.roll.pack(fill='both',expand=True)
            self.ghost_button.state(['!disabled'])
    def view_change(self,e=None):
        self.capture_view()
        self.end_audition();self.roll.key_held=False;self.roll.preview_pitch=None
        self.project.ui['view']=self.view_var.get()
        self.roll.drag=None;self.roll.vel_drag=False
        self.roll.sync_zoom()
        self.show_view()
        self.roll.redraw();self.overview.redraw()
        self.restore_editor_view()
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
        follow=self.player.playing and self.project.ui.get('follow_playhead',True)
        overview=self.project.ui.get('view')=='All Tracks'
        self.roll.cursor(tick,follow=follow and not overview)
        self.overview.cursor(tick,follow=follow and overview)
    def remember_track_click(self,event):
        self._track_click_index=self.list.nearest(event.y)
    def select_track(self,e):
        selection=list(self.list.curselection())
        if not selection:return
        clicked=getattr(self,'_track_click_index',None)
        self._track_click_index=None
        active=clicked if clicked in selection else self.list.index('active')
        if active not in selection:active=selection[-1]
        if selection==self.project.ui.get('track_selection') and active==self.project.ui['selected']:
            return
        changed_active=active!=self.project.ui['selected']
        if changed_active:self.end_audition()
        self.project.ui['selected']=active
        self.project.ui['track_selection']=selection
        self.sync_ui(clear_notes=changed_active)
    def toggle_play_state(self,attr):
        values=[getattr(self.project.tracks[i],attr) for i in self.selected_track_indices()]
        self.set_play_state(attr,not all(values))
    def set_play_state(self,attr,value):
        def action():
            if attr not in ('muted','solo'):raise ValueError('不正な再生状態です')
            indices=self.selected_track_indices()
            if all(getattr(self.project.tracks[i],attr)==value for i in indices):return
            self.checkpoint()
            for i in indices:setattr(self.project.tracks[i],attr,bool(value))
            self.player.set_track_states(self.project.tracks)
            if not audible_tracks(self.project.tracks)[self.project.ui['selected']]:self.end_audition()
            self.changed();self.sync_ui(clear_notes=False)
        self.guarded(action)
    def checkpoint(self): self.history.push(self.project)
    def changed(self):
        self.dirty=True
        self.title(f'JUNO Sketch • {self.path.name if self.path else "Untitled"} *')
    def track_values(self):
        vals={k:int(v.get()) for k,v in self.fields.items()}
        vals['channel']-=1;vals['program']-=1
        if not (0<=vals['channel']<16 and 0<=vals['program']<128 and all(0<=vals[k]<=127 for k in ('msb','lsb')) and 1<=vals['velocity']<=127):
            raise ValueError('設定値が範囲外です')
        return vals
    def update_patch_label(self):
        try:
            msb=int(self.fields['msb'].get())
            lsb=int(self.fields['lsb'].get())
            program=int(self.fields['program'].get())-1
            patch=patch_names.lookup(msb,lsb,program)
            prefix='GM' if self.project.ui['output']=='Internal Preview' else 'JUNO'
            text=f"{prefix}: {patch['name']} ({patch['bank']})" if patch else f'{prefix}: 未登録のBank / Program' 
        except ValueError:
            text='JUNO: —'
        self.patch_label.set(text)
    def naming_change(self):
        self.checkpoint()
        self.track.auto_name=self.auto_name_var.get()
        self.changed()
    def apply_patch_name(self):
        def action():
            indices=self.selected_track_indices()
            if len(indices)>1:
                known=[i for i in indices if patch_names.lookup(self.project.tracks[i].msb,
                        self.project.tracks[i].lsb,self.project.tracks[i].program)]
                if not known:
                    self.status.set('選択トラックに登録済み音色がありません。名前は変更しません。')
                    return
                self.checkpoint()
                for i in known:patch_names.apply_name(self.project.tracks[i])
                self.changed();self.sync_ui(clear_notes=False)
                self.status.set(f'{len(known)}トラックに音色名を適用（未登録 {len(indices)-len(known)}、MIDI送信なし）')
                return
            vals=self.track_values()
            patch=patch_names.lookup(vals['msb'],vals['lsb'],vals['program'])
            if patch is None:
                self.status.set('未登録のBank / Programです。トラック名は変更しません。')
                return
            self.checkpoint()
            for k,v in vals.items():setattr(self.track,k,v)
            self.track.auto_name=self.auto_name_var.get()
            patch_names.apply_name(self.track)
            self.changed();self.sync_ui()
            self.status.set('音色名をトラック名に適用しました（MIDI送信なし）')
        self.guarded(action)
    def apply_track(self):
        def action():
            vals=self.track_values()
            self.stop();self.checkpoint()
            for k,v in vals.items():setattr(self.track,k,v)
            self.track.name=self.name_var.get().strip() or self.track.name
            self.track.auto_name=self.auto_name_var.get()
            if self.track.auto_name:patch_names.apply_name(self.track)
            self.changed();self.sync_ui()
            self.ensure_output().setup(self.track)
        self.guarded(action)
    def change_meter(self,bar,numerator,denominator):
        signatures=set_at_bar(self.project.signatures,bar,numerator,denominator)
        self.commit_meter(signatures)
    def commit_meter(self,signatures):
        if signatures==self.project.signatures:return
        self.stop();self.checkpoint()
        self.project.signatures=signatures
        self.changed();self.sync_ui()
        self.status.set('拍子を変更しました。ノートのtick位置は維持しています。')
    def meter_dialog(self):
        dialog=tk.Toplevel(self)
        dialog.title('Time Signature')
        dialog.transient(self)
        frame=ttk.Frame(dialog,padding=12);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='拍子変更（小節番号で指定）').pack(anchor='w')
        changes=tk.Listbox(frame,width=42,height=8,exportselection=False)
        changes.pack(fill='both',expand=True,pady=8)
        row=ttk.Frame(frame);row.pack(fill='x')
        bar=tk.StringVar(value=str(MeterMap(self.project.signatures).position(self.playhead)[0]))
        numerator=tk.StringVar(value='4');denominator=tk.StringVar(value='4')
        ttk.Label(row,text='小節').pack(side='left')
        ttk.Spinbox(row,textvariable=bar,from_=1,to=99999,width=7).pack(side='left',padx=5)
        ttk.Spinbox(row,textvariable=numerator,from_=1,to=255,width=5).pack(side='left')
        ttk.Label(row,text='/').pack(side='left',padx=5)
        ttk.Combobox(row,textvariable=denominator,values=[1,2,4,8,16,32,64,128,256],state='readonly',width=5).pack(side='left')
        def refresh():
            changes.delete(0,'end')
            for segment in MeterMap(self.project.signatures).segments:
                changes.insert('end',f'小節 {segment.bar}    {segment.numerator}/{segment.denominator}    tick {segment.tick}')
        def select(event):
            if changes.curselection():
                s=MeterMap(self.project.signatures).segments[changes.curselection()[0]]
                bar.set(s.bar);numerator.set(s.numerator);denominator.set(s.denominator)
        def apply():
            self.change_meter(int(bar.get()),int(numerator.get()),int(denominator.get()))
            refresh()
        def remove():
            if changes.curselection():
                s=MeterMap(self.project.signatures).segments[changes.curselection()[0]]
                self.commit_meter(remove_at_bar(self.project.signatures,s.bar));refresh()
        changes.bind('<<ListboxSelect>>',select)
        buttons=ttk.Frame(frame);buttons.pack(fill='x',pady=8)
        ttk.Button(buttons,text='設定',command=lambda:self.guarded(apply)).pack(side='left')
        ttk.Button(buttons,text='選択した変更を削除',command=lambda:self.guarded(remove)).pack(side='left',padx=6)
        ttk.Button(buttons,text='閉じる',command=dialog.destroy).pack(side='right')
        ttk.Label(frame,text='ノートのtick位置は移動しません。BPMは4分音符基準です。').pack(anchor='w')
        current=MeterMap(self.project.signatures).segment(self.playhead)
        numerator.set(current.numerator);denominator.set(current.denominator)
        refresh();dialog.grab_set()
        dialog.bind('<Escape>',lambda e:dialog.destroy())
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
            destination=self.output_var.get()
            port=self.port.get()
            if destination==self.project.ui['output'] and port==self.project.ui.get('port',''):
                return
            self.stop();self.release_output();self.checkpoint()
            switched=switch_destination(self.project,destination)
            self.project.ui['port']=port
            self.changed();self.sync_ui()
            if destination=='JUNO-DS' and not port:
                self.status.set('JUNOの基本バンクを設定しました。MIDIポートを選択してください。')
                return
            try:
                out=self.ensure_output()
                for track in self.project.tracks:
                    out.setup(track)
            except Exception as exc:
                # Retain the selected mode/settings; retry on reconnect/play.
                if self.output:
                    try:self.release_output()
                    except Exception:self.output=None
                self.status.set(f'出力の初期化に失敗しました: {exc}')
                return
            label='GM基本バンク' if destination=='Internal Preview' else 'JUNOバンク'
            self.status.set(f'{label}を適用・送信しました' if switched else 'MIDIポートを変更しました')
        self.guarded(action)
    def ensure_output(self):
        if self.output is None:
            self.output=InternalPreviewOutput() if self.project.ui['output']=='Internal Preview' else JunoDsOutput(self.project.ui.get('port',''))
        return self.output
    def end_audition(self):
        if self.audition_job:
            self.after_cancel(self.audition_job);self.audition_job=None
        if self.audition_preview is not None:
            self.player.end_preview(self.audition_preview);self.audition_preview=None
        if self.audition_note and self.output:
            ch,pitch=self.audition_note
            self.audition_note=None
            self.output.send(mido.Message('note_off',channel=ch,note=pitch))
    def audition(self,pitch,velocity,hold=False):
        if not audible_tracks(self.project.tracks)[self.project.ui['selected']]:return
        try:
            self.end_audition()
            if self.player.playing:
                token=self.player.begin_preview(self.project.ui['selected'],pitch,velocity)
                if token is None:return
                self.audition_preview=token
            else:
                out=self.ensure_output();out.setup(self.track)
                out.send(mido.Message('note_on',channel=self.track.channel,note=pitch,velocity=velocity))
                self.audition_note=(self.track.channel,pitch)
            if not hold:self.audition_job=self.after(170,lambda:self.guarded(self.end_audition))
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
        self.stop();self.playhead=tick;self.player.position=tick;self.draw_cursors(tick)
    def poll(self):
        if self.player.playing:
            cursor=self.player.cursor();self.draw_cursors(cursor)
            bar,beat,tick,n,d=MeterMap(self.project.signatures).position(cursor)
            self.status.set(f'Playing  {bar}|{beat}   tick {tick}   {n}/{d}')
        if self.was_playing and not self.player.playing:
            self.playhead=int(self.player.position);self.draw_cursors(self.playhead)
            self.status.set('Stopped')
        self.was_playing=self.player.playing
        while not self.player.errors.empty():
            self.status.set('出力エラー: '+self.player.errors.get())
        self.after(25,self.poll)
    def install_transport_keys(self):
        # Tk runs widget/class bindings before toplevel bindings. Intercept
        # transport keys first so a focused checkbox/button cannot also activate.
        tag='TransportKeys'
        self.bind_class(tag,'<KeyPress-space>',self.space)
        self.bind_class(tag,'<KeyRelease-space>',self.space_release)
        self.bind_class(tag,'<Return>',self.return_to_start)
        self.bind_class(tag,'<KP_Enter>',self.return_to_start)
        for key,attr in [('s','solo'),('S','solo'),('m','muted'),('M','muted')]:
            self.bind_class(tag,f'<KeyPress-{key}>',lambda e,a=attr:self.track_state_key(e,a))
        def install(widget):
            widget.bindtags((tag,)+widget.bindtags())
            for child in widget.winfo_children():install(child)
        install(self)
    def track_state_key(self,event,attr):
        # Keep text editing and Command/Control shortcuts (notably Save) intact.
        if self.text_focus() or event.state & 0x0c:return
        self.toggle_play_state(attr)
        return 'break'
    def space_release(self,event):
        if not self.text_focus():return 'break'
    def return_to_start(self,event):
        if self.text_focus():return
        # Track selection always exists; here “unselected” means no selected notes.
        if self.project.ui.get('view')!='All Tracks' and self.roll.selected:return 'break'
        self.set_playhead(0)
        self.roll.xview('moveto',0)
        self.overview.canvas.xview_moveto(0)
        self.status.set('Stopped  1|1')
        return 'break'
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
        self.roll.preview_pitch=None;self.roll.key_held=False
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
        ui=self.project.ui
        ui.update(geometry=self.geometry(),overview_xview=self.overview.canvas.xview()[0])
        if ui.get('view')!='All Tracks':
            prefix='drum_' if ui.get('view')=='Drum Editor' else ''
            ui[prefix+'xview']=self.roll.canvas.xview()[0]
            ui[prefix+'yview']=self.roll.canvas.yview()[0]
    def restore_editor_view(self):
        ui=self.project.ui
        prefix='drum_' if ui.get('view')=='Drum Editor' else ''
        self.roll.xview('moveto',ui.get(prefix+'xview',0))
        self.roll.canvas.yview_moveto(ui.get(prefix+'yview',0 if prefix else 0.43))
        self.overview.canvas.xview_moveto(ui.get('overview_xview',0))
    def restore_view(self):
        if 'geometry' in self.project.ui:self.geometry(self.project.ui['geometry'])
        self.restore_editor_view()
    def close(self):
        if self.confirm_discard():
            self.stop();self.release_output();self.destroy()
