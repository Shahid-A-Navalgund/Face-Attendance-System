"""
MODULE 4: ADMIN DASHBOARD
GUI for managing students and viewing attendance reports

All data is fetched from Firebase once per sync (in a background thread) and
every tab renders from that snapshot, so the window never freezes.
"""

import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font as tkfont
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, db
import pandas as pd
import pytz
import config

IST = pytz.timezone('Asia/Kolkata')
DATE_FMT = '%d-%m-%Y'          # date key format written by 03_mark_attendance.py
DATASET = 'dataset'
MIN_ATTENDANCE = 75            # % below which a student is flagged
AUTO_REFRESH_MS = 60_000

C = {
    'bg': '#f1f5f9', 'card': '#ffffff', 'border': '#e2e8f0', 'stripe': '#f8fafc',
    'text': '#0f172a', 'muted': '#64748b',
    'sidebar': '#0f172a', 'sidebar_active': '#1e293b', 'sidebar_text': '#94a3b8',
    'accent': '#4f46e5', 'accent_dark': '#4338ca', 'accent_soft': '#e0e7ff',
    'green': '#16a34a', 'red': '#dc2626', 'red_soft': '#fee2e2', 'amber': '#d97706',
}


def parse_date(text):
    try:
        return datetime.strptime(str(text)[:10], DATE_FMT).date()
    except ValueError:
        return None


def today():
    return datetime.now(IST).date()


def as_dict(node):
    """Firebase returns a list when keys look like 0,1,2...; normalise to dict."""
    if isinstance(node, list):
        return {str(i): v for i, v in enumerate(node) if v is not None}
    return node or {}


class AttendanceData:
    """One snapshot of the Firebase database."""

    def __init__(self, students=None, attendance=None):
        self.students = {sid: info for sid, info in as_dict(students).items() if isinstance(info, dict)}
        self.attendance = {sid: as_dict(recs) for sid, recs in as_dict(attendance).items()}
        # Any date on which at least one student was marked counts as a class day
        self.class_days = sorted({d for recs in self.attendance.values()
                                  for d in map(parse_date, recs) if d})

    @classmethod
    def fetch(cls):
        root = as_dict(db.reference('/').get())
        return cls(root.get('students'), root.get('attendance'))

    def all_ids(self):
        return sorted(set(self.students) | set(self.attendance))

    def name(self, sid):
        if sid in self.students:
            return self.students[sid].get('name', 'Unknown')
        recs = self.attendance.get(sid, {})
        return next((r.get('name') for r in recs.values() if isinstance(r, dict)), 'Unknown')

    def record(self, sid, day):
        rec = self.attendance.get(sid, {}).get(day.strftime(DATE_FMT))
        return rec if isinstance(rec, dict) else None

    def records_on(self, day):
        """[(sid, name, time)] of everyone marked present on `day`."""
        return [(sid, self.name(sid), rec.get('time', '—'))
                for sid in self.all_ids() if (rec := self.record(sid, day))]

    def present_dates(self, sid):
        return sorted(d for d in map(parse_date, self.attendance.get(sid, {})) if d)

    def class_days_for(self, sid):
        """Class days since the student registered (earlier days aren't absences)."""
        registered = parse_date(self.students.get(sid, {}).get('registered_date', ''))
        return [d for d in self.class_days if not registered or d >= registered]

    def percent(self, sid):
        days = self.class_days_for(sid)
        return len(self.present_dates(sid)) / len(days) * 100 if days else None


class AdminDashboard:
    def __init__(self, root):
        self.root = root
        root.title('Attendance Admin')
        root.geometry('1180x760')
        root.minsize(980, 640)
        root.configure(bg=C['bg'])

        self.data = AttendanceData()
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.loading = None
        self.report_df = None
        self.sort_state = {}
        self.firebase_error = self._init_firebase()

        self._setup_fonts()
        self._setup_styles()
        self._build()
        self.show('overview')

        root.protocol('WM_DELETE_WINDOW', self._close)
        if self.firebase_error:
            self._set_status(False, 'Firebase not connected')
            root.after(300, lambda: messagebox.showerror(
                'Firebase', f'Could not connect to Firebase:\n\n{self.firebase_error}'))
        else:
            self.refresh()
            root.after(AUTO_REFRESH_MS, self._auto_refresh)

    # ------------------------------------------------------------------ setup

    def _init_firebase(self):
        try:
            firebase_admin.get_app()
        except ValueError:
            try:
                cred = credentials.Certificate(config.SERVICE_ACCOUNT_KEY)
                firebase_admin.initialize_app(cred, {'databaseURL': config.FIREBASE_DATABASE_URL})
            except Exception as e:
                return str(e)
        return None

    def _setup_fonts(self):
        families = set(tkfont.families())
        family = next((f for f in ('SF Pro Text', 'Helvetica Neue', 'Segoe UI', 'Helvetica')
                       if f in families), 'TkDefaultFont')
        sizes = {'h1': (22, 'bold'), 'h2': (14, 'bold'), 'body': (12, 'normal'),
                 'bold': (12, 'bold'), 'small': (11, 'normal'), 'stat': (30, 'bold'),
                 'brand': (17, 'bold')}
        self.F = {k: (family, size, weight) for k, (size, weight) in sizes.items()}

    def _setup_styles(self):
        s = ttk.Style()
        s.theme_use('clam')
        s.configure('.', font=self.F['body'], background=C['bg'], foreground=C['text'])

        s.configure('Treeview', background=C['card'], fieldbackground=C['card'],
                    foreground=C['text'], rowheight=34, borderwidth=0, font=self.F['body'])
        s.layout('Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])
        s.map('Treeview', background=[('selected', C['accent_soft'])],
              foreground=[('selected', C['text'])])
        s.configure('Treeview.Heading', background=C['card'], foreground=C['muted'],
                    font=self.F['small'], relief='flat', borderwidth=0, padding=(8, 8))
        s.map('Treeview.Heading', background=[('active', C['bg'])])

        for name, bg, hover, fg, border in (
                ('Accent', C['accent'], C['accent_dark'], 'white', C['accent']),
                ('Ghost', C['card'], C['bg'], C['text'], C['border']),
                ('Danger', C['card'], C['red_soft'], C['red'], C['border'])):
            s.configure(f'{name}.TButton', background=bg, foreground=fg, bordercolor=border,
                        lightcolor=bg, darkcolor=bg, focuscolor=bg, padding=(14, 7),
                        font=self.F['bold'], relief='flat')
            s.map(f'{name}.TButton',
                  background=[('disabled', C['border']), ('active', hover)],
                  lightcolor=[('active', hover)], darkcolor=[('active', hover)],
                  foreground=[('disabled', C['muted'])])

        s.configure('Seg.Toolbutton', background=C['card'], foreground=C['text'],
                    padding=(16, 7), font=self.F['bold'], relief='flat', borderwidth=0)
        s.map('Seg.Toolbutton', background=[('selected', C['accent']), ('active', C['bg'])],
              foreground=[('selected', 'white')])

        for widget in ('TEntry', 'TCombobox'):
            s.configure(widget, fieldbackground=C['card'], background=C['card'],
                        bordercolor=C['border'], lightcolor=C['border'], darkcolor=C['border'],
                        arrowcolor=C['muted'], padding=6)
            s.map(widget, bordercolor=[('focus', C['accent'])], lightcolor=[('focus', C['accent'])],
                  fieldbackground=[('readonly', C['card'])], background=[('readonly', C['card'])])

        s.configure('Vertical.TScrollbar', background=C['border'], troughcolor=C['card'],
                    bordercolor=C['card'], arrowcolor=C['muted'], lightcolor=C['border'],
                    darkcolor=C['border'])

    # ---------------------------------------------------------------- widgets

    def label(self, parent, text='', font='body', fg='text', bg='card', **kw):
        return tk.Label(parent, text=text, font=self.F[font], fg=C.get(fg, fg),
                        bg=C.get(bg, bg), **kw)

    def card(self, parent):
        return tk.Frame(parent, bg=C['card'], highlightthickness=1,
                        highlightbackground=C['border'], highlightcolor=C['border'])

    def table(self, parent, columns, widths=None):
        wrap = tk.Frame(parent, bg=C['card'])
        tree = ttk.Treeview(wrap, show='headings', selectmode='browse')
        bar = ttk.Scrollbar(wrap, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        tree.pack(side='left', fill='both', expand=True)
        bar.pack(side='right', fill='y')
        tree.tag_configure('odd', background=C['stripe'])
        tree.tag_configure('present', foreground=C['green'])
        tree.tag_configure('absent', foreground=C['red'])
        self.set_columns(tree, columns, widths)
        return wrap, tree

    def set_columns(self, tree, columns, widths=None):
        tree['columns'] = columns
        for i, col in enumerate(columns):
            tree.heading(col, text=col.upper(), anchor='w',
                         command=lambda c=col: self.sort_tree(tree, c))
            tree.column(col, width=(widths[i] if widths else 140), anchor='w', stretch=True)

    def fill(self, tree, rows, tag_fn=None, iids=None):
        tree.delete(*tree.get_children())
        for i, row in enumerate(rows):
            tags = (['odd'] if i % 2 else []) + (tag_fn(row) if tag_fn else [])
            tree.insert('', 'end', iid=iids[i] if iids else None, values=row, tags=tags)

    def sort_tree(self, tree, col):
        reverse = self.sort_state.get((str(tree), col), False)

        def key(value):
            if (d := parse_date(value)):
                return (0, d.toordinal(), '')
            try:
                return (0, float(str(value).rstrip('%')), '')
            except ValueError:
                return (1, 0, str(value).lower())

        items = sorted(tree.get_children(''), key=lambda k: key(tree.set(k, col)), reverse=reverse)
        for i, item in enumerate(items):
            tree.move(item, '', i)
            tags = [t for t in tree.item(item, 'tags') if t != 'odd'] + (['odd'] if i % 2 else [])
            tree.item(item, tags=tags)
        self.sort_state[(str(tree), col)] = not reverse

    def header(self, page, title, subtitle=''):
        head = tk.Frame(page, bg=C['bg'])
        head.pack(fill='x', padx=32, pady=(28, 16))
        text = tk.Frame(head, bg=C['bg'])
        text.pack(side='left')
        self.label(text, title, 'h1', bg='bg').pack(anchor='w')
        sub = self.label(text, subtitle, 'small', 'muted', 'bg')
        sub.pack(anchor='w', pady=(2, 0))
        actions = tk.Frame(head, bg=C['bg'])
        actions.pack(side='right')
        return sub, actions

    # ----------------------------------------------------------------- layout

    def _build(self):
        side = tk.Frame(self.root, bg=C['sidebar'], width=220)
        side.pack(side='left', fill='y')
        side.pack_propagate(False)

        tk.Label(side, text='◉  Attendance', font=self.F['brand'], fg='white',
                 bg=C['sidebar'], anchor='w').pack(fill='x', padx=24, pady=(28, 0))
        tk.Label(side, text='Admin console', font=self.F['small'], fg=C['sidebar_text'],
                 bg=C['sidebar'], anchor='w').pack(fill='x', padx=24, pady=(2, 28))

        self.nav = {}
        for key, text in (('overview', 'Overview'), ('students', 'Students'),
                          ('reports', 'Reports'), ('about', 'About')):
            item = tk.Label(side, text=text, font=self.F['bold'], fg=C['sidebar_text'],
                            bg=C['sidebar'], anchor='w', padx=16, pady=10, cursor='hand2')
            item.pack(fill='x', padx=12, pady=2)
            item.bind('<Button-1>', lambda e, k=key: self.show(k))
            item.bind('<Enter>', lambda e, w=item: w.config(fg='white'))
            item.bind('<Leave>', lambda e, k=key, w=item: w.config(
                fg='white' if k == self.current else C['sidebar_text']))
            self.nav[key] = item

        bottom = tk.Frame(side, bg=C['sidebar'])
        bottom.pack(side='bottom', fill='x', padx=24, pady=24)
        self.status = tk.Label(bottom, font=self.F['small'], bg=C['sidebar'],
                               anchor='w', justify='left')
        self.status.pack(fill='x')
        self.refresh_btn = ttk.Button(bottom, text='Refresh', style='Accent.TButton',
                                      command=self.refresh)
        self.refresh_btn.pack(fill='x', pady=(10, 0))

        main = tk.Frame(self.root, bg=C['bg'])
        main.pack(side='left', fill='both', expand=True)
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)

        self.pages = {}
        for key, build in (('overview', self._build_overview), ('students', self._build_students),
                           ('reports', self._build_reports), ('about', self._build_about)):
            page = tk.Frame(main, bg=C['bg'])
            page.grid(row=0, column=0, sticky='nsew')
            build(page)
            self.pages[key] = page

    def show(self, key):
        self.current = key
        self.pages[key].tkraise()
        for k, item in self.nav.items():
            active = k == key
            item.config(bg=C['sidebar_active'] if active else C['sidebar'],
                        fg='white' if active else C['sidebar_text'])

    # --------------------------------------------------------------- overview

    def _build_overview(self, page):
        self.ov_sub, _ = self.header(page, 'Overview')
        body = tk.Frame(page, bg=C['bg'])
        body.pack(fill='both', expand=True, padx=32, pady=(0, 28))

        stats = tk.Frame(body, bg=C['bg'])
        stats.pack(fill='x')
        self.stats = {}
        for i, (key, title, color) in enumerate((
                ('total', 'Registered students', 'accent'), ('present', 'Present today', 'green'),
                ('absent', 'Absent today', 'red'), ('rate', 'Attendance rate', 'amber'))):
            stats.grid_columnconfigure(i, weight=1, uniform='stats')
            box = self.card(stats)
            box.grid(row=0, column=i, sticky='nsew', padx=(0 if i == 0 else 12, 0))
            tk.Frame(box, bg=C[color], height=4).pack(fill='x')
            self.label(box, title, 'small', 'muted').pack(anchor='w', padx=20, pady=(16, 0))
            value = self.label(box, '—', 'stat')
            value.pack(anchor='w', padx=20, pady=(0, 16))
            self.stats[key] = value

        lower = tk.Frame(body, bg=C['bg'])
        lower.pack(fill='both', expand=True, pady=(16, 0))
        lower.grid_columnconfigure(0, weight=3, uniform='lower')
        lower.grid_columnconfigure(1, weight=2, uniform='lower')
        lower.grid_rowconfigure(0, weight=1)
        lower.grid_rowconfigure(1, weight=1)

        present = self.card(lower)
        present.grid(row=0, column=0, rowspan=2, sticky='nsew', padx=(0, 12))
        self.label(present, 'Present today', 'h2').pack(anchor='w', padx=20, pady=(16, 8))
        wrap, self.present_tree = self.table(present, ('Name', 'ID', 'Time'), (220, 150, 100))
        wrap.pack(fill='both', expand=True, padx=12, pady=(0, 12))

        trend = self.card(lower)
        trend.grid(row=0, column=1, sticky='nsew', pady=(0, 6))
        self.label(trend, 'Last 7 days', 'h2').pack(anchor='w', padx=20, pady=(16, 0))
        self.chart = tk.Canvas(trend, bg=C['card'], highlightthickness=0, height=150)
        self.chart.pack(fill='both', expand=True, padx=20, pady=(4, 12))
        self.chart.bind('<Configure>', lambda e: self._draw_chart())

        absent = self.card(lower)
        absent.grid(row=1, column=1, sticky='nsew', pady=(6, 0))
        self.label(absent, 'Not marked today', 'h2').pack(anchor='w', padx=20, pady=(16, 8))
        wrap, self.absent_tree = self.table(absent, ('Name', 'ID'), (180, 140))
        wrap.pack(fill='both', expand=True, padx=12, pady=(0, 12))

    def _render_overview(self):
        day = today()
        present = self.data.records_on(day)
        present_ids = {sid for sid, _, _ in present}
        registered = set(self.data.students)
        total = len(registered)
        here = len(registered & present_ids)

        self.stats['total'].config(text=total)
        self.stats['present'].config(text=len(present))
        self.stats['absent'].config(text=total - here)
        self.stats['rate'].config(text=f'{here / total * 100:.0f}%' if total else '—')
        self.ov_sub.config(text=day.strftime('%A, %d %B %Y'), fg=C['muted'])

        self.fill(self.present_tree, [(name, sid, time) for sid, name, time in present])
        self.fill(self.absent_tree, [(self.data.name(sid), sid)
                                     for sid in sorted(registered - present_ids)], lambda r: ['absent'])
        self._draw_chart()

    def _draw_chart(self):
        c = self.chart
        c.delete('all')
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50 or h < 60:
            return
        days = [today() - timedelta(days=i) for i in range(6, -1, -1)]
        counts = [len(self.data.records_on(d)) for d in days]
        top = max(max(counts), 1)
        slot, base = w / 7, h - 22
        bar_w = min(34, slot * 0.55)
        for i, (day, n) in enumerate(zip(days, counts)):
            x = slot * i + slot / 2
            bar_h = max((base - 22) * n / top, 3)
            color = C['accent'] if i == 6 else C['accent_soft']
            c.create_rectangle(x - bar_w / 2, base - bar_h, x + bar_w / 2, base, fill=color, outline='')
            c.create_text(x, base - bar_h - 10, text=n, font=self.F['small'], fill=C['muted'])
            c.create_text(x, base + 12, text=day.strftime('%a'), font=self.F['small'],
                          fill=C['text'] if i == 6 else C['muted'])

    # --------------------------------------------------------------- students

    def _build_students(self, page):
        self.st_sub, actions = self.header(page, 'Students')
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', lambda *_: self._render_students())
        self.label(actions, 'Search', 'small', 'muted', 'bg').pack(side='left', padx=(0, 6))
        ttk.Entry(actions, textvariable=self.search_var, width=24).pack(side='left', padx=(0, 12))
        ttk.Button(actions, text='View history', style='Ghost.TButton',
                   command=self.show_history).pack(side='left', padx=(0, 8))
        ttk.Button(actions, text='Delete', style='Danger.TButton',
                   command=self.delete_student).pack(side='left')

        box = self.card(page)
        box.pack(fill='both', expand=True, padx=32, pady=(0, 28))
        wrap, self.students_tree = self.table(
            box, ('ID', 'Name', 'Department', 'Registered', 'Days present', 'Attendance'),
            (150, 220, 110, 120, 110, 110))
        wrap.pack(fill='both', expand=True, padx=12, pady=12)
        self.students_tree.bind('<Double-1>', lambda e: self.show_history())

    def _render_students(self):
        query = self.search_var.get().strip().lower()
        rows, ids = [], []
        for sid in sorted(self.data.students):
            info = self.data.students[sid]
            name = info.get('name', '—')
            if query and query not in sid.lower() and query not in name.lower():
                continue
            pct = self.data.percent(sid)
            rows.append((sid, name, info.get('department', '—'),
                         str(info.get('registered_date', '—'))[:10],
                         len(self.data.present_dates(sid)),
                         f'{pct:.0f}%' if pct is not None else '—'))
            ids.append(sid)

        def tags(row):
            return ['absent'] if row[5] != '—' and float(row[5][:-1]) < MIN_ATTENDANCE else []

        self.fill(self.students_tree, rows, tags, ids)
        self.st_sub.config(text=f'{len(rows)} of {len(self.data.students)} students  ·  '
                                f'red = below {MIN_ATTENDANCE}% attendance  ·  double-click for history')

    def _selected_student(self):
        selection = self.students_tree.selection()
        if not selection:
            messagebox.showinfo('Students', 'Select a student first.')
            return None
        return selection[0]

    def show_history(self):
        sid = self._selected_student()
        if not sid:
            return
        name = self.data.name(sid)
        days = self.data.class_days_for(sid)
        pct = self.data.percent(sid)

        win = tk.Toplevel(self.root)
        win.title(f'{name} — attendance')
        win.geometry('560x580')
        win.configure(bg=C['bg'])
        win.transient(self.root)
        self.label(win, name, 'h1', bg='bg').pack(anchor='w', padx=24, pady=(20, 0))
        summary = f'{sid}  ·  present {len(self.data.present_dates(sid))} of {len(days)} class days'
        if pct is not None:
            summary += f' ({pct:.0f}%)'
        self.label(win, summary, 'small', 'muted', 'bg').pack(anchor='w', padx=24, pady=(2, 12))

        box = self.card(win)
        box.pack(fill='both', expand=True, padx=24, pady=(0, 24))
        wrap, tree = self.table(box, ('Date', 'Day', 'Time', 'Status'), (120, 120, 100, 100))
        wrap.pack(fill='both', expand=True, padx=12, pady=12)
        rows = []
        for day in reversed(days):
            rec = self.data.record(sid, day)
            rows.append((day.strftime(DATE_FMT), day.strftime('%A'),
                         rec.get('time', '—') if rec else '—', 'Present' if rec else 'Absent'))
        self.fill(tree, rows, lambda r: ['present' if r[3] == 'Present' else 'absent'])

    def delete_student(self):
        sid = self._selected_student()
        if not sid:
            return
        name = self.data.name(sid)
        folders = ([f for f in os.listdir(DATASET) if f.startswith(f'student_{sid}_')]
                   if os.path.isdir(DATASET) else [])
        msg = (f'Delete {name} ({sid})?\n\nThis removes the student and all their attendance '
               f'records from Firebase')
        msg += f', plus {len(folders)} face-image folder(s).' if folders else '.'
        if not messagebox.askyesno('Delete student', msg + '\n\nThis cannot be undone.', icon='warning'):
            return
        try:
            db.reference(f'students/{sid}').delete()
            db.reference(f'attendance/{sid}').delete()
            for folder in folders:
                shutil.rmtree(os.path.join(DATASET, folder))
        except Exception as e:
            messagebox.showerror('Delete failed', str(e))
            return
        note = '\n\nRun 02_train_model.py again so the model forgets this face.' if folders else ''
        messagebox.showinfo('Deleted', f'{name} was removed.{note}')
        self.refresh()

    # ---------------------------------------------------------------- reports

    def _build_reports(self, page):
        self.rp_sub, actions = self.header(page, 'Reports', '')
        ttk.Button(actions, text='Export all records', style='Ghost.TButton',
                   command=self.export_all).pack(side='left', padx=(0, 8))
        ttk.Button(actions, text='Export this report', style='Accent.TButton',
                   command=self.export_report).pack(side='left')

        bar = tk.Frame(page, bg=C['bg'])
        bar.pack(fill='x', padx=32, pady=(0, 12))
        self.report_type = tk.StringVar(value='daily')
        seg = tk.Frame(bar, bg=C['border'])
        seg.pack(side='left')
        for value, text in (('daily', 'Daily'), ('monthly', 'Monthly'), ('summary', 'All-time summary')):
            ttk.Radiobutton(seg, text=text, value=value, variable=self.report_type,
                            style='Seg.Toolbutton', command=self._render_report
                            ).pack(side='left', padx=1, pady=1)

        self.daily_ctl = tk.Frame(bar, bg=C['bg'])
        self.day_var = tk.StringVar(value=today().strftime(DATE_FMT))
        ttk.Button(self.daily_ctl, text='‹', width=2, style='Ghost.TButton',
                   command=lambda: self._shift_day(-1)).pack(side='left')
        day_entry = ttk.Entry(self.daily_ctl, textvariable=self.day_var, width=11, justify='center')
        day_entry.pack(side='left', padx=6)
        day_entry.bind('<Return>', lambda e: self._render_report())
        ttk.Button(self.daily_ctl, text='›', width=2, style='Ghost.TButton',
                   command=lambda: self._shift_day(1)).pack(side='left')
        ttk.Button(self.daily_ctl, text='Today', style='Ghost.TButton',
                   command=lambda: self._shift_day(None)).pack(side='left', padx=(6, 0))

        self.month_ctl = tk.Frame(bar, bg=C['bg'])
        self.month_var = tk.StringVar()
        self.month_box = ttk.Combobox(self.month_ctl, textvariable=self.month_var,
                                      state='readonly', width=16)
        self.month_box.pack(side='left')
        self.month_box.bind('<<ComboboxSelected>>', lambda e: self._render_report())
        self.months = {}

        box = self.card(page)
        box.pack(fill='both', expand=True, padx=32, pady=(0, 28))
        wrap, self.report_tree = self.table(box, ('Report',))
        wrap.pack(fill='both', expand=True, padx=12, pady=12)

    def _shift_day(self, delta):
        day = parse_date(self.day_var.get()) or today()
        day = today() if delta is None else day + timedelta(days=delta)
        self.day_var.set(day.strftime(DATE_FMT))
        self._render_report()

    def _render_report(self):
        kind = self.report_type.get()
        self.daily_ctl.pack_forget()
        self.month_ctl.pack_forget()
        if kind == 'daily':
            self.daily_ctl.pack(side='left', padx=16)
            df = self._daily_report()
        elif kind == 'monthly':
            self.month_ctl.pack(side='left', padx=16)
            df = self._monthly_report()
        else:
            df = self._summary_report()
        if df is None:
            return
        self.report_df = df
        columns = list(df.columns)

        def tags(row):
            values = dict(zip(columns, row))
            if values.get('Status') == 'Present':
                return ['present']
            if values.get('Status') in ('Absent', f'Below {MIN_ATTENDANCE}%'):
                return ['absent']
            pct = str(values.get('Attendance', '—')).rstrip('%')
            return ['absent'] if pct != '—' and float(pct) < MIN_ATTENDANCE else []

        self.set_columns(self.report_tree, columns)
        self.fill(self.report_tree, df.astype(str).values.tolist(), tags)

    def _daily_report(self):
        day = parse_date(self.day_var.get().strip())
        if not day:
            self.rp_sub.config(text='Enter the date as DD-MM-YYYY', fg=C['red'])
            return None
        rows = []
        for sid in self.data.all_ids():
            rec = self.data.record(sid, day)
            rows.append({'Student ID': sid, 'Name': self.data.name(sid),
                         'Status': 'Present' if rec else 'Absent',
                         'Time': rec.get('time', '') if rec else ''})
        df = pd.DataFrame(rows, columns=['Student ID', 'Name', 'Status', 'Time'])
        present = int((df['Status'] == 'Present').sum())
        self.rp_sub.config(fg=C['muted'], text=f'{day:%A, %d %B %Y}  ·  {present} present  ·  '
                                               f'{len(df) - present} absent')
        return df

    def _monthly_report(self):
        months = {(d.year, d.month) for d in self.data.class_days} | {(today().year, today().month)}
        self.months = {datetime(y, m, 1).strftime('%B %Y'): (y, m) for y, m in sorted(months, reverse=True)}
        self.month_box['values'] = list(self.months)
        if self.month_var.get() not in self.months:
            self.month_var.set(next(iter(self.months)))
        ym = self.months[self.month_var.get()]

        rows = []
        for sid in self.data.all_ids():
            days = [d for d in self.data.class_days_for(sid) if (d.year, d.month) == ym]
            present = sum(1 for d in self.data.present_dates(sid) if (d.year, d.month) == ym)
            rows.append({'Student ID': sid, 'Name': self.data.name(sid), 'Days present': present,
                         'Class days': len(days),
                         'Attendance': f'{present / len(days) * 100:.0f}%' if days else '—'})
        month_days = sum(1 for d in self.data.class_days if (d.year, d.month) == ym)
        self.rp_sub.config(fg=C['muted'], text=f'{self.month_var.get()}  ·  {month_days} class days')
        return pd.DataFrame(rows, columns=['Student ID', 'Name', 'Days present', 'Class days', 'Attendance'])

    def _summary_report(self):
        rows = []
        for sid in self.data.all_ids():
            pct = self.data.percent(sid)
            rows.append({'Student ID': sid, 'Name': self.data.name(sid),
                         'Days present': len(self.data.present_dates(sid)),
                         'Class days': len(self.data.class_days_for(sid)),
                         'Attendance': f'{pct:.0f}%' if pct is not None else '—',
                         'Status': ('—' if pct is None else
                                    'OK' if pct >= MIN_ATTENDANCE else f'Below {MIN_ATTENDANCE}%')})
        self.rp_sub.config(fg=C['muted'], text=f'{len(self.data.class_days)} class days recorded  ·  '
                                               f'students below {MIN_ATTENDANCE}% are shown in red')
        return pd.DataFrame(rows, columns=['Student ID', 'Name', 'Days present', 'Class days',
                                           'Attendance', 'Status'])

    def _save(self, df, name):
        if df is None or df.empty:
            messagebox.showinfo('Export', 'Nothing to export yet.')
            return
        path = filedialog.asksaveasfilename(
            defaultextension='.xlsx', initialfile=name,
            filetypes=[('Excel files', '*.xlsx'), ('CSV files', '*.csv')])
        if not path:
            return
        try:
            if path.endswith('.csv'):
                df.to_csv(path, index=False)
            else:
                df.to_excel(path, index=False, sheet_name='Attendance')
            messagebox.showinfo('Export', f'Saved to\n{path}')
        except Exception as e:
            messagebox.showerror('Export failed', str(e))

    def export_report(self):
        kind = self.report_type.get()
        suffix = {'daily': self.day_var.get(), 'monthly': self.month_var.get().replace(' ', '_'),
                  'summary': today().strftime(DATE_FMT)}[kind]
        self._save(self.report_df, f'attendance_{kind}_{suffix}')

    def export_all(self):
        records = [{'Student ID': sid, 'Name': self.data.name(sid), 'Date': date,
                    'Time': rec.get('time', ''), 'Status': rec.get('status', 'Present')}
                   for sid, recs in self.data.attendance.items()
                   for date, rec in recs.items() if isinstance(rec, dict)]
        df = pd.DataFrame(records)
        if not df.empty:
            df['_day'] = df['Date'].map(parse_date)
            df = df.sort_values(['_day', 'Student ID']).drop(columns='_day')
        self._save(df, f'attendance_all_{today().strftime(DATE_FMT)}')

    # ------------------------------------------------------------------ about

    def _build_about(self, page):
        self.header(page, 'About', 'Face recognition attendance · OpenCV LBPH + Firebase')
        body = tk.Frame(page, bg=C['bg'])
        body.pack(fill='both', expand=True, padx=32, pady=(0, 28))
        body.grid_columnconfigure(0, weight=1, uniform='about')
        body.grid_columnconfigure(1, weight=1, uniform='about')

        sections = (
            ('How it works', [
                '1.  Register students — python 01_face_registration.py',
                '2.  Train the model — python 02_train_model.py',
                '3.  Mark attendance — python 03_mark_attendance.py',
                '4.  Review and export here',
            ]),
            ('Tips', [
                '•  Capture at least 30 images per student',
                '•  Retrain after adding or deleting students',
                '•  Use even, front-facing light',
                f'•  Students below {MIN_ATTENDANCE}% are flagged in red',
                f'•  Data refreshes automatically every {AUTO_REFRESH_MS // 1000}s',
            ]),
        )
        for i, (title, lines) in enumerate(sections):
            box = self.card(body)
            box.grid(row=0, column=i, sticky='nsew', padx=(0 if i == 0 else 12, 0))
            self.label(box, title, 'h2').pack(anchor='w', padx=20, pady=(16, 8))
            for line in lines:
                self.label(box, line, justify='left', anchor='w').pack(fill='x', padx=20, pady=3)
            tk.Frame(box, bg=C['card'], height=12).pack()

        conn = self.card(body)
        conn.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(12, 0))
        self.label(conn, 'Database', 'h2').pack(anchor='w', padx=20, pady=(16, 4))
        self.label(conn, config.FIREBASE_DATABASE_URL, 'small', 'muted').pack(anchor='w', padx=20, pady=(0, 16))

    # ------------------------------------------------------------------- sync

    def _set_status(self, ok, text):
        self.status.config(text=f'●  {text}', fg='#4ade80' if ok else '#f87171')

    def refresh(self):
        if self.firebase_error or (self.loading and not self.loading.done()):
            return
        self._set_status(True, 'Syncing…')
        self.refresh_btn.state(['disabled'])
        self.loading = self.pool.submit(AttendanceData.fetch)
        self._poll()

    def _poll(self):
        if not self.loading.done():
            self.root.after(100, self._poll)
            return
        self.refresh_btn.state(['!disabled'])
        try:
            self.data = self.loading.result()
        except Exception as e:
            self._set_status(False, 'Sync failed')
            self.ov_sub.config(text=f'Could not load data: {e}', fg=C['red'])
            return
        self._set_status(True, f'Synced {datetime.now(IST):%H:%M:%S}')
        self._render_overview()
        self._render_students()
        self._render_report()

    def _auto_refresh(self):
        self.refresh()
        self.root.after(AUTO_REFRESH_MS, self._auto_refresh)

    def _close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main():
    root = tk.Tk()
    AdminDashboard(root)
    root.mainloop()


if __name__ == '__main__':
    main()
