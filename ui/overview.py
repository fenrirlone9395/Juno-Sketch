"""Read-only, sixteen-lane playback overview. Editing lives in PianoRoll."""
import tkinter as tk
from models.project import PPQ
from services.meter import MeterMap
from ui.track_colors import track_color, project_end


class TrackOverview(tk.Frame):
    LABEL = 165
    SCALE = 0.10

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.position = 0
        self.ruler = tk.Canvas(self, height=28, bg='#20252d', highlightthickness=0)
        self.canvas = tk.Canvas(self, bg='#20252d', highlightthickness=0)
        self.labels = tk.Canvas(self.canvas, width=self.LABEL, bg='#20252d', highlightthickness=0)
        self.labels.place(x=0, y=0, width=self.LABEL, relheight=1)
        self.scrollbar = tk.Scrollbar(self, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=self.scrolled)
        self.ruler.grid(row=0, column=0, sticky='ew')
        self.canvas.grid(row=1, column=0, sticky='nsew')
        self.scrollbar.grid(row=2, column=0, sticky='ew')
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.canvas.bind('<Configure>', lambda e: self.redraw())
        self.canvas.bind('<Button-1>', self.select)
        self.canvas.bind('<Double-Button-1>', self.edit)
        self.labels.bind('<Button-1>', self.select)
        self.labels.bind('<Double-Button-1>', self.edit)
        self.canvas.bind('<MouseWheel>', self.wheel)
        self.ruler.bind('<Button-1>', self.seek)

    def lane_height(self):
        return max(1, self.canvas.winfo_height()) / 16

    def scrolled(self, first, last):
        self.scrollbar.set(first, last)
        self.draw_ruler()

    def draw_ruler(self):
        self.ruler.delete('all')
        offset = self.canvas.canvasx(0)
        meter = MeterMap(self.app.project.signatures)
        start = max(0, int((offset-self.LABEL)/self.SCALE))
        end = start+int(max(1,self.canvas.winfo_width())/self.SCALE)+PPQ
        for tick,bar,beat,n,d in meter.beats(start,end):
            x = self.LABEL + tick*self.SCALE-offset
            if beat==1 or PPQ*4/d*self.SCALE>=40:
                self.ruler.create_text(x+3, 13, text=f'{bar}|{beat}', anchor='w', fill='#e3e8f0')
        self.ruler.create_rectangle(0, 0, self.LABEL, 28, fill='#20252d', outline='')
        self.ruler.create_text(8, 13, text='ALL TRACKS', anchor='w', fill='#c5cedb')

    def redraw(self):
        c = self.canvas
        c.delete('all')
        self.labels.delete('all')
        project = self.app.project
        meter = MeterMap(project.signatures)
        end_tick = meter.extent(project_end(project),project.ui.get('bars',8))
        width = self.LABEL + end_tick*self.SCALE
        height = max(1, c.winfo_height())
        c.configure(scrollregion=(0, 0, width, height))
        lane = self.lane_height()
        for i, track in enumerate(project.tracks):
            y = i*lane
            active = i == project.ui['selected']
            bg = '#353e4b' if active else ('#242b34' if i % 2 else '#20252d')
            c.create_rectangle(0, y, width, y+lane, fill=bg, outline='#434b59', tags=('lane',))
            self.labels.create_rectangle(0, y, self.LABEL, y+lane, fill=bg, outline='#434b59')
            self.labels.create_rectangle(3, y+3, 7, y+lane-3, fill=track_color(i), outline='')
            self.labels.create_text(13, y+lane/2, text=f'{i+1:02}  {track.name}  [Ch {track.channel+1}]',
                                    anchor='w', fill=track_color(i), width=self.LABEL-18)
        for tick,bar,beat,n,d in meter.beats(0,end_tick):
            x = self.LABEL + tick*self.SCALE
            c.create_line(x, 0, x, height, fill='#525d6d' if beat==1 else '#303946',tags='meter_line')
        for i, track in enumerate(project.tracks):
            low = min((n.pitch for n in track.notes), default=60)-2
            high = max((n.pitch for n in track.notes), default=72)+2
            for note in track.notes:
                x = self.LABEL + note.start*self.SCALE
                y = i*lane+4+(high-note.pitch)/(high-low)*max(1, lane-10)
                c.create_rectangle(x, y, max(x+2, x+note.duration*self.SCALE), y+3,
                                   fill=track_color(i), outline='', tags=('overview_note', f'track_{i}'))
        self.draw_ruler()
        self.cursor(self.position)

    def cursor(self, tick, follow=False):
        self.position = tick
        c = self.canvas
        c.delete('playhead')
        x = self.LABEL+tick*self.SCALE
        if follow:
            left = c.canvasx(0)
            available = max(1, c.winfo_width()-self.LABEL)
            if x < left+self.LABEL or x > left+c.winfo_width()-20:
                total = float(c.cget('scrollregion').split()[2])
                c.xview_moveto(max(0, (x-self.LABEL-available*.15)/total))
        c.create_line(x, 0, x, max(1, c.winfo_height()), fill='#ff6b73', width=2, tags='playhead')

    def select(self, event):
        self.canvas.focus_set()
        index = min(15, max(0, int(event.y/self.lane_height())))
        self.app.project.ui['selected'] = index
        self.app.sync_ui()

    def edit(self, event):
        self.select(event)
        self.app.view_var.set('Piano Roll')
        self.app.view_change()

    def seek(self, event):
        if event.x < self.LABEL:
            return
        self.app.set_playhead(max(0, round((self.canvas.canvasx(event.x)-self.LABEL)/self.SCALE)))

    def wheel(self, event):
        self.canvas.xview_scroll(-1 if event.delta > 0 else 1, 'units')
