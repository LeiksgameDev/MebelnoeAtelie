"""
ООО "Мебельное ателье" г. Киров — учет товаров.
Технологии: Python + SQLite + CustomTkinter.
"""
import csv
import os
import re
import random
import sqlite3
import subprocess
import sys
import tempfile
import webbrowser
from urllib.parse import quote
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import customtkinter as ctk

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = Path(__file__).resolve().parent
    RESOURCE_DIR = APP_DIR

DB_PATH = APP_DIR / "mebelnoe_atelie.db"
CSV_PATH = RESOURCE_DIR / "data" / "materialy.csv"
LOGO_PATH = RESOURCE_DIR / "assets" / "logo.png"
ICON_DARK_PATH = RESOURCE_DIR / "assets" / "brightness_4.png"
ICON_LIGHT_PATH = RESOURCE_DIR / "assets" / "brightness_5.png"

ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = "admin123"
EMPLOYEE_LOGIN = "employee"
EMPLOYEE_PASSWORD = "employee123"
ROLE_ADMIN = "admin"
ROLE_EMPLOYEE = "employee"


LIGHT = {
    "bg": "#FFFFFF", "bg2": "#FFF8F3", "red": "#E53935", "orange": "#FF8A00",
    "text": "#1F2937", "text2": "#6B7280", "border": "#E5E7EB"
}
DARK = {
    "bg": "#121212", "bg2": "#1E1E1E", "red": "#FF5A52", "orange": "#FF9F1C",
    "text": "#F5F5F5", "text2": "#BDBDBD", "border": "#2D2D2D"
}

PRODUCT_TYPES = {
    "Шкафы": [
        "Прямые (линейные)", "Угловые", "Радиусные (гнутые)", "Распашные (классика)",
        "Шкафы-купе (раздвижные)", "Гармошки (складные)", "Шкафы-пеналы с выдвижным механизмом"
    ],
    "Кухни": [
        "Линейная (прямая)", "Угловая (Г-образная)", "П-образная", "Параллельная (двухрядная)",
        "С островом", "Полуостровная"
    ],
    "Фасады": [
        "ЛДСП в пленке", "МДФ в пленке ПВХ", "Крашеный МДФ (эмаль)", "Пластик (акрил/полимер)",
        "Рамочные (профиль + вставка)", "Массив дерева", "Корпусная (сборная)",
        "Модульная (готовая)", "Встроенная (на заказ)"
    ]
}

EXPENSE_NORMS = {
    "Кухня прямая 3 метра": 5.0,
    "Угловая кухня 5 метров": 6.0,
    "Шкаф купе": 3.0,
    "Одежный шкаф": 1.0,
    "Шкаф для документов": 1.0,
    "Стол": 1.0,
    "Тумба": 0.25,
    "Комод": 1.0,
}


def digits_only(value: str) -> str:
    return ''.join(ch for ch in value if ch.isdigit())


def normalize_phone_digits(value: str) -> str:
    """Возвращает 10 цифр номера РФ без префикса 7/8, если номер введен полностью."""
    digits = digits_only(value)
    if len(digits) == 11 and digits[0] in ("7", "8"):
        digits = digits[1:]
    return digits


def format_phone(value: str) -> str:
    """Маска телефона применяется только после полного ввода номера."""
    raw = value.strip()
    digits = normalize_phone_digits(raw)
    if not raw:
        return ""
    if len(digits) != 10:
        return raw
    return f"+7({digits[:3]}){digits[3:6]}-{digits[6:8]}-{digits[8:10]}"


def normalize_article(value: str) -> str:
    """Если артикул материала не указан, сохраняем Н/Д. Комментарии не трогаем."""
    value = (value or "").strip()
    return value if value else "Н/Д"


def is_valid_phone(value: str) -> bool:
    value = value.strip()
    if not value:
        return True
    return bool(re.fullmatch(r"\+7\(\d{3}\)\d{3}-\d{2}-\d{2}", format_phone(value)))


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, login TEXT UNIQUE, password TEXT, role TEXT DEFAULT 'employee');
        CREATE TABLE IF NOT EXISTS materials(
            id INTEGER PRIMARY KEY, material TEXT, manufacturer TEXT, color TEXT, color_code TEXT,
            size TEXT, thickness TEXT, quantity REAL DEFAULT 0, note TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS suppliers(
            id INTEGER PRIMARY KEY, name TEXT UNIQUE, phone TEXT DEFAULT '', email TEXT DEFAULT '', address TEXT DEFAULT '', note TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS receipts(
            id INTEGER PRIMARY KEY, date TEXT, material_id INTEGER, supplier_id INTEGER, quantity REAL, price REAL, note TEXT,
            FOREIGN KEY(material_id) REFERENCES materials(id), FOREIGN KEY(supplier_id) REFERENCES suppliers(id)
        );
        CREATE TABLE IF NOT EXISTS expenses(
            id INTEGER PRIMARY KEY, date TEXT, material_id INTEGER, product_type TEXT, product_subtype TEXT, quantity REAL, note TEXT,
            FOREIGN KEY(material_id) REFERENCES materials(id)
        );
        ''')
        for ddl in (
            "ALTER TABLE expenses ADD COLUMN item_count REAL DEFAULT 1",
            "ALTER TABLE expenses ADD COLUMN sheets_per_item REAL DEFAULT 0"
        ):
            try:
                con.execute(ddl)
            except sqlite3.OperationalError:
                pass
        try:
            con.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'employee'")
        except sqlite3.OperationalError:
            pass
        con.execute("INSERT OR IGNORE INTO users(login,password,role) VALUES(?,?,?)", (ADMIN_LOGIN, ADMIN_PASSWORD, ROLE_ADMIN))
        con.execute("INSERT OR IGNORE INTO users(login,password,role) VALUES(?,?,?)", (EMPLOYEE_LOGIN, EMPLOYEE_PASSWORD, ROLE_EMPLOYEE))
        con.execute("UPDATE users SET role=? WHERE login=?", (ROLE_ADMIN, ADMIN_LOGIN))
        con.execute("UPDATE users SET role=? WHERE login=?", (ROLE_EMPLOYEE, EMPLOYEE_LOGIN))
        # Для материалов: пустой артикул автоматически заменяется на "Н/Д".
        # Примечания/комментарии при этом остаются пустыми строками.
        con.execute("UPDATE materials SET color_code='Н/Д' WHERE color_code IS NULL OR TRIM(color_code)='' ")
        count = con.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        if count == 0 and CSV_PATH.exists():
            with open(CSV_PATH, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            for r in rows:
                con.execute('''INSERT INTO materials(material,manufacturer,color,color_code,size,thickness,quantity)
                               VALUES(?,?,?,?,?,?,?)''', (
                    r.get("Материал", ""), r.get("Производитель", ""), r.get("Цвет", ""),
                    normalize_article(r.get("Код цвета (артикул)", "")), r.get("Размер (Д x Ш), мм", ""), r.get("Толщина, мм", ""), random.randint(1, 100)
                ))
            for name in sorted({r.get("Производитель", "").strip() for r in rows if r.get("Производитель", "").strip()}):
                con.execute("INSERT OR IGNORE INTO suppliers(name,note) VALUES(?,?)", (name, "Создано автоматически из Excel"))


def apply_tree_style(p):
    """Оформление стандартных таблиц ttk под активную тему CustomTkinter."""
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        "App.Treeview",
        background=p["bg2"],
        foreground=p["text"],
        fieldbackground=p["bg2"],
        bordercolor=p["border"],
        borderwidth=1,
        rowheight=30,
        font=("Arial", 10),
    )
    style.configure(
        "App.Treeview.Heading",
        background=p["red"],
        foreground="#FFFFFF",
        relief="flat",
        font=("Arial", 10, "bold"),
    )
    style.map(
        "App.Treeview",
        background=[("selected", p["orange"])],
        foreground=[("selected", "#FFFFFF")],
    )
    style.map(
        "App.Treeview.Heading",
        background=[("active", p["orange"])],
        foreground=[("active", "#FFFFFF")],
    )
    style.configure(
        "App.Vertical.TScrollbar",
        gripcount=0,
        background=p["bg2"],
        darkcolor=p["border"],
        lightcolor=p["border"],
        troughcolor=p["bg"],
        bordercolor=p["border"],
        arrowcolor=p["text"],
    )




def as_cell_text(value):
    return "" if value is None else str(value)


class ExcelFilterMixin:
    """Фильтр по значениям столбца через кнопку в заголовке таблицы."""

    def init_excel_filters(self):
        self.column_filters = {}
        self.numeric_filters = {}

    def heading_text(self, title, col):
        active = self.column_filters.get(col) is not None or self.numeric_filters.get(col) is not None
        mark = "●" if active else "▼"
        return f"{title} {mark}"

    def ask_numeric_value(self, title, mode, on_apply, initial=""):
        p = self.app.palette
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.geometry("320x180")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.configure(fg_color=p["bg"])

        ctk.CTkLabel(dlg, text=title, text_color=p["text"], font=("Arial", 15, "bold")).pack(anchor="w", padx=16, pady=(16, 8))
        entry = ctk.CTkEntry(dlg, placeholder_text="Введите число")
        entry.pack(fill="x", padx=16, pady=(0, 12))
        if initial not in (None, ""):
            entry.insert(0, str(initial))

        def apply_value():
            raw = entry.get().strip()
            try:
                value = float(raw.replace(',', '.'))
            except ValueError:
                messagebox.showerror("Ошибка", "Введите корректное число")
                return
            dlg.destroy()
            on_apply(mode, value)

        actions = ctk.CTkFrame(dlg, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(actions, text="Отмена", fg_color=p["orange"], command=dlg.destroy).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="Применить", fg_color=p["red"], command=apply_value).pack(side="right", padx=4)
        entry.bind("<Return>", lambda _e: apply_value())
        entry.focus_set()

    def open_column_filter(self, col, title):
        if not hasattr(self, "all_rows") and not hasattr(self, "all_table_rows"):
            return
        rows = getattr(self, "all_rows", getattr(self, "all_table_rows", []))
        values = sorted({as_cell_text(r[col]) for r in rows}, key=lambda x: x.lower())
        current = self.column_filters.get(col)
        selected = set(values if current is None else current)

        win = ctk.CTkToplevel(self)
        win.title(f"Фильтр: {title}")
        win.geometry("340x480")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        p = self.app.palette
        win.configure(fg_color=p["bg"])

        ctk.CTkLabel(win, text=f"Фильтр по столбцу: {title}", text_color=p["text"], font=("Arial", 15, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        search = ctk.CTkEntry(win, placeholder_text="Поиск значения...")
        search.pack(fill="x", padx=12, pady=(0, 8))

        holder = ctk.CTkScrollableFrame(win, fg_color=p["bg2"], border_color=p["border"], border_width=1)
        holder.pack(fill="both", expand=True, padx=12, pady=8)
        checks = {}

        def render():
            for w in holder.winfo_children():
                w.destroy()
            needle = search.get().strip().lower()
            for value in values:
                if needle and needle not in value.lower():
                    continue
                var = tk.BooleanVar(value=value in selected)
                cb = ctk.CTkCheckBox(holder, text=value if value else "(пусто)", variable=var, text_color=p["text"], fg_color=p["red"], hover_color=p["orange"])
                cb.pack(anchor="w", padx=8, pady=4)
                checks[value] = var

        def sync_visible():
            for value, var in checks.items():
                if var.get():
                    selected.add(value)
                else:
                    selected.discard(value)

        def select_visible(flag=True):
            for var in checks.values():
                var.set(flag)
            sync_visible()

        def apply():
            sync_visible()
            self.column_filters[col] = None if len(selected) == len(values) else set(selected)
            win.destroy()
            self.refresh_headings()
            self.apply_filters()

        def reset_one():
            self.column_filters[col] = None
            win.destroy()
            self.refresh_headings()
            self.apply_filters()

        search.bind("<KeyRelease>", lambda _e: (sync_visible(), checks.clear(), render()))
        render()

        if title.lower().strip() == "остаток" or col == "quantity":
            numeric_box = ctk.CTkFrame(win, fg_color=p["bg2"], border_color=p["border"], border_width=1)
            numeric_box.pack(fill="x", padx=12, pady=(0, 8))
            ctk.CTkLabel(numeric_box, text="Фильтр по числу", text_color=p["text"], font=("Arial", 13, "bold")).pack(anchor="w", padx=8, pady=(8, 4))
            def set_numeric_filter(mode, value=None):
                self.numeric_filters[col] = (mode, value)
                win.destroy()
                self.refresh_headings()
                self.apply_filters()

            numeric_actions = ctk.CTkFrame(numeric_box, fg_color="transparent")
            numeric_actions.pack(fill="x", padx=8, pady=4)
            ctk.CTkButton(
                numeric_actions, text="Меньше...", fg_color=p["orange"],
                command=lambda: self.ask_numeric_value("Меньше числа", "lt", set_numeric_filter)
            ).pack(side="left", fill="x", expand=True, padx=(0, 4))
            ctk.CTkButton(
                numeric_actions, text="Больше...", fg_color=p["orange"],
                command=lambda: self.ask_numeric_value("Больше числа", "gt", set_numeric_filter)
            ).pack(side="left", fill="x", expand=True, padx=(4, 0))
            preset_row = ctk.CTkFrame(numeric_box, fg_color="transparent")
            preset_row.pack(fill="x", padx=8, pady=(2, 8))
            ctk.CTkButton(preset_row, text="= 0", width=70, command=lambda: set_numeric_filter("eq", 0)).pack(side="left", padx=3)
            ctk.CTkButton(preset_row, text="≠ 0", width=70, command=lambda: set_numeric_filter("ne", 0)).pack(side="left", padx=3)
            ctk.CTkButton(preset_row, text="Сброс числа", fg_color=p["orange"], command=lambda: (self.numeric_filters.update({col: None}), win.destroy(), self.refresh_headings(), self.apply_filters())).pack(side="left", padx=3)

        actions = ctk.CTkFrame(win, fg_color="transparent")
        actions.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(actions, text="Все", width=70, command=lambda: select_visible(True)).pack(side="left", padx=3)
        ctk.CTkButton(actions, text="Снять", width=70, command=lambda: select_visible(False)).pack(side="left", padx=3)
        ctk.CTkButton(actions, text="Сброс", width=70, fg_color=p["orange"], command=reset_one).pack(side="left", padx=3)
        ctk.CTkButton(actions, text="Применить", fg_color=p["red"], command=apply).pack(side="right", padx=3)

    def value_passes_column_filters(self, row):
        for col, allowed in self.column_filters.items():
            if allowed is not None and as_cell_text(row[col]) not in allowed:
                return False
        for col, rule in self.numeric_filters.items():
            if rule is None:
                continue
            mode, number = rule
            try:
                value = float(str(row[col]).replace(',', '.'))
            except Exception:
                return False
            if mode == "lt" and not value < number:
                return False
            if mode == "eq" and not value == number:
                return False
            if mode == "ne" and not value != number:
                return False
            if mode == "gt" and not value > number:
                return False
        return True


class CRUDTab(ExcelFilterMixin, ctk.CTkFrame):
    def __init__(self, master, app, table, columns, labels):
        super().__init__(master, fg_color="transparent")
        self.app, self.table, self.columns, self.labels = app, table, columns, labels
        self.entries = {}
        self.all_rows = []
        self.init_excel_filters()
        self.selected_id = None
        self.can_edit = getattr(app, "user_role", ROLE_ADMIN) == ROLE_ADMIN or table not in ("materials", "suppliers")
        self.build()
        self.refresh()

    def build(self):
        p = self.app.palette
        actions_top = ctk.CTkFrame(self, fg_color=p["bg2"], border_color=p["border"], border_width=1)
        actions_top.pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(
            actions_top,
            text="Двойной клик ЛКМ — редактировать, ПКМ — меню записи",
            text_color=p["text2"]
        ).pack(side="left", padx=10, pady=10)
        if self.can_edit:
            ctk.CTkButton(actions_top, text="Добавить новую запись", fg_color=p["red"], command=self.open_add_window).pack(side="right", padx=8, pady=8)
        else:
            ctk.CTkLabel(actions_top, text="Режим просмотра", text_color=p["text2"]).pack(side="right", padx=10, pady=10)

        frame = ctk.CTkFrame(self, fg_color=p["bg"])
        frame.pack(fill="both", expand=True, padx=12, pady=8)
        self.tree = ttk.Treeview(frame, columns=self.columns, show="headings", style="App.Treeview")
        for col, title in zip(self.columns, self.labels):
            self.tree.heading(col, text=self.heading_text(title, col), command=lambda c=col, t=title: self.open_column_filter(c, t))
            self.tree.column(col, width=125)
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(frame, command=self.tree.yview, style="App.Vertical.TScrollbar")
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<<TreeviewSelect>>", self.pick)
        self.tree.bind("<Double-1>", self.open_edit_window)
        self.tree.bind("<Button-3>", self.show_context_menu)


    def show_context_menu(self, event):
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        self.tree.selection_set(row_id)
        self.tree.focus(row_id)
        self.selected_id = row_id
        menu = tk.Menu(self, tearoff=0)
        if self.can_edit:
            menu.add_command(label="Редактировать запись", command=self.open_edit_window)
            menu.add_command(label="Удалить запись", command=self.delete)
        if self.table == "suppliers":
            if self.can_edit:
                menu.add_separator()
            menu.add_command(label="Написать на почту", command=self.write_supplier_email)
        if not self.can_edit and self.table != "suppliers":
            return
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def get_selected_supplier_email(self):
        if self.table != "suppliers" or not self.selected_id:
            return ""
        with db() as con:
            row = con.execute("SELECT email FROM suppliers WHERE id=?", (self.selected_id,)).fetchone()
        return (row["email"] or "").strip() if row else ""

    def write_supplier_email(self):
        email = self.get_selected_supplier_email()
        if not email:
            messagebox.showwarning("Почта", "У поставщика не указана эл.почта")
            return
        p = self.app.palette
        win = ctk.CTkToplevel(self)
        win.title("Написать на почту")
        win.geometry("420x260")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.configure(fg_color=p["bg"])
        ctk.CTkLabel(win, text=f"Выберите почтовый ящик для письма:\n{email}", text_color=p["text"], font=("Arial", 15, "bold")).pack(anchor="w", padx=16, pady=(16, 12))

        def open_url(url):
            webbrowser.open(url)
            win.destroy()

        subject = quote("Письмо от ООО Мебельное ателье")
        to = quote(email)
        options = [
            ("Почтовая программа", f"mailto:{email}?subject={subject}"),
            ("Gmail", f"https://mail.google.com/mail/?view=cm&fs=1&to={to}&su={subject}"),
            ("Яндекс Почта", f"https://mail.yandex.ru/compose?mailto={to}&subject={subject}"),
            ("Mail.ru", f"https://e.mail.ru/compose/?to={to}&subject={subject}"),
        ]
        for title, url in options:
            ctk.CTkButton(win, text=title, fg_color=p["red"] if title == "Почтовая программа" else p["orange"], command=lambda u=url: open_url(u)).pack(fill="x", padx=16, pady=4)


    def refresh_headings(self):
        if not hasattr(self, "tree"):
            return
        for col, title in zip(self.columns, self.labels):
            self.tree.heading(col, text=self.heading_text(title, col), command=lambda c=col, t=title: self.open_column_filter(c, t))

    def apply_filters(self):
        if not hasattr(self, "tree"):
            return
        self.tree.delete(*self.tree.get_children())
        for r in self.all_rows:
            if self.value_passes_column_filters(r):
                self.tree.insert("", "end", iid=str(r["id"]), values=[r[c] for c in self.columns])

    def on_phone_change(self, _=None):
        entry = self.entries.get("phone")
        if not entry:
            return
        formatted = format_phone(entry.get())
        entry.delete(0, "end")
        entry.insert(0, formatted)
        entry.icursor("end")

    def get_column_suggestions(self, col):
        """Возвращает уникальные значения из текущей таблицы для быстрого заполнения полей."""
        if self.table != "materials" or col not in self.columns:
            return []
        try:
            with db() as con:
                rows = con.execute(
                    f"SELECT DISTINCT {col} FROM {self.table} WHERE COALESCE({col}, '') <> '' ORDER BY {col}"
                ).fetchall()
            return [str(r[0]) for r in rows if str(r[0]).strip()]
        except Exception:
            return []

    def attach_suggestion_box(self, parent, row_index, col, entry):
        """Добавляет кнопку автозаполнения справа от поля ввода без второго поля."""
        suggestions = self.get_column_suggestions(col)
        if not suggestions:
            return
        p = self.app.palette

        def show_suggestions():
            popup = ctk.CTkToplevel(self)
            popup.title("Автозаполнение")
            popup.geometry("320x360")
            popup.transient(self.winfo_toplevel())
            popup.grab_set()
            popup.configure(fg_color=p["bg"])
            ctk.CTkLabel(
                popup,
                text=f"Выберите значение: {self.labels[self.columns.index(col)]}",
                text_color=p["text"],
                font=("Arial", 14, "bold"),
            ).pack(anchor="w", padx=12, pady=(12, 6))

            search = ctk.CTkEntry(popup, placeholder_text="Поиск...")
            search.pack(fill="x", padx=12, pady=(0, 8))

            list_frame = ctk.CTkScrollableFrame(popup, fg_color=p["bg2"], border_color=p["border"], border_width=1)
            list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

            def fill_buttons(values):
                for child in list_frame.winfo_children():
                    child.destroy()
                for value in values:
                    ctk.CTkButton(
                        list_frame,
                        text=value,
                        anchor="w",
                        fg_color=p["bg"],
                        hover_color=p["orange"],
                        text_color=p["text"],
                        command=lambda v=value: (self.apply_suggestion_value(entry, v), popup.destroy()),
                    ).pack(fill="x", padx=6, pady=3)

            def filter_values(_event=None):
                q = search.get().strip().lower()
                fill_buttons([v for v in suggestions if q in v.lower()])

            search.bind("<KeyRelease>", filter_values)
            fill_buttons(suggestions)
            search.focus_set()

        ctk.CTkButton(
            parent,
            text="▼",
            width=38,
            fg_color=p["orange"],
            hover_color=p["red"],
            command=show_suggestions,
        ).grid(row=row_index, column=2, sticky="w", padx=(0, 12), pady=8)

    @staticmethod
    def apply_suggestion_value(entry, value):
        if not value or value == "Выбрать...":
            return
        entry.delete(0, "end")
        entry.insert(0, value)
        entry.icursor("end")

    def prepare_values(self, entries):
        vals = [entries[c].get().strip() for c in self.columns]
        if self.table == "materials" and "color_code" in self.columns:
            article_index = self.columns.index("color_code")
            vals[article_index] = normalize_article(vals[article_index])
        # Примечание/note специально остается пустым, если пользователь ничего не ввел.
        if self.table == "suppliers" and "phone" in self.columns:
            phone_index = self.columns.index("phone")
            vals[phone_index] = format_phone(vals[phone_index])
        return vals

    def values(self):
        return self.prepare_values(self.entries)

    def validate(self):
        if self.table == "suppliers" and "phone" in self.columns:
            phone = self.entries["phone"].get().strip()
            if phone and not is_valid_phone(format_phone(phone)):
                messagebox.showerror("Ошибка", "Номер телефона должен быть в формате +7(999)123-45-67")
                return False
        return True

    def duplicate_exists(self, con, vals, exclude_id=None):
        data = {c: (vals[i] if i < len(vals) else "") for i, c in enumerate(self.columns)}
        params = []
        where = []

        def norm(v):
            return (v or "").strip().lower()

        if self.table == "materials":
            check_cols = [c for c in ("material", "manufacturer", "color", "size", "thickness") if c in self.columns]
            if not check_cols:
                return False
            for c in check_cols:
                where.append(f"LOWER(TRIM(COALESCE({c},'')))=?")
                params.append(norm(data.get(c)))
        elif self.table == "suppliers":
            checks = []
            name = norm(data.get("name"))
            email = norm(data.get("email"))
            phone = norm(data.get("phone"))
            if name:
                checks.append("LOWER(TRIM(COALESCE(name,'')))=?")
                params.append(name)
            if email and email != "н/д":
                checks.append("LOWER(TRIM(COALESCE(email,'')))=?")
                params.append(email)
            if phone and phone != "н/д":
                checks.append("LOWER(TRIM(COALESCE(phone,'')))=?")
                params.append(phone)
            if not checks:
                return False
            where.append("(" + " OR ".join(checks) + ")")
        else:
            return False

        if exclude_id is not None:
            where.append("id<>?")
            params.append(exclude_id)
        sql = f"SELECT id FROM {self.table} WHERE " + " AND ".join(where) + " LIMIT 1"
        return con.execute(sql, params).fetchone() is not None

    def duplicate_message(self):
        if self.table == "materials":
            return "Материал с такими параметрами уже есть в базе данных."
        if self.table == "suppliers":
            return "Поставщик с такими данными уже есть в базе данных."
        return "Данная запись уже есть в базе данных."

    def refresh(self):
        with db() as con:
            self.all_rows = con.execute(f"SELECT id,{','.join(self.columns)} FROM {self.table} ORDER BY id DESC").fetchall()
        self.apply_filters()

    def pick(self, _=None):
        item = self.tree.focus()
        self.selected_id = item if item else None

    def clear(self):
        self.selected_id = None
        if hasattr(self, "tree"):
            for item in self.tree.selection():
                self.tree.selection_remove(item)


    def open_edit_window(self, _event=None):
        if not self.can_edit:
            return
        item = self.tree.focus()
        if not item:
            return
        self.selected_id = item
        with db() as con:
            row = con.execute(f"SELECT {','.join(self.columns)} FROM {self.table} WHERE id=?", (self.selected_id,)).fetchone()
        if not row:
            messagebox.showwarning("Выбор", "Запись не найдена")
            self.refresh()
            return

        p = self.app.palette
        win = ctk.CTkToplevel(self)
        win.title("Редактирование записи")
        win.geometry("560x520")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.configure(fg_color=p["bg"])
        entries = {}
        ctk.CTkLabel(win, text="Редактирование записи", text_color=p["text"], font=("Arial", 18, "bold")).pack(anchor="w", padx=16, pady=(16, 8))
        body = ctk.CTkFrame(win, fg_color=p["bg2"], border_color=p["border"], border_width=1)
        body.pack(fill="both", expand=True, padx=16, pady=8)
        for i, col in enumerate(self.columns):
            ctk.CTkLabel(body, text=self.labels[i], text_color=p["text"]).grid(row=i, column=0, sticky="w", padx=12, pady=8)
            e = ctk.CTkEntry(body, width=330)
            e.grid(row=i, column=1, sticky="ew", padx=12, pady=8)
            value = row[col] if row[col] is not None else ""
            e.insert(0, str(value))
            entries[col] = e
            if self.table == "suppliers" and col == "phone":
                def phone_mask(_event=None, entry=e):
                    formatted = format_phone(entry.get())
                    entry.delete(0, "end")
                    entry.insert(0, formatted)
                    entry.icursor("end")
                e.bind("<FocusOut>", phone_mask)
        body.grid_columnconfigure(1, weight=1)

        def save_edit():
            vals = self.prepare_values(entries)
            if self.table == "suppliers" and "phone" in self.columns:
                phone_index = self.columns.index("phone")
                vals[phone_index] = format_phone(vals[phone_index])
                if vals[phone_index] and not is_valid_phone(vals[phone_index]):
                    messagebox.showerror("Ошибка", "Номер телефона должен быть в формате +7(999)123-45-67")
                    return
            with db() as con:
                if self.duplicate_exists(con, vals, self.selected_id):
                    messagebox.showwarning("Запись уже существует", self.duplicate_message())
                    return
                con.execute(f"UPDATE {self.table} SET {','.join(c+'=?' for c in self.columns)} WHERE id=?", vals + [self.selected_id])
            win.destroy()
            self.refresh()
            self.app.refresh_all()

        actions = ctk.CTkFrame(win, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=(4, 16))
        ctk.CTkButton(actions, text="Отмена", command=win.destroy).pack(side="right", padx=5)
        ctk.CTkButton(actions, text="Сохранить", fg_color=p["red"], command=save_edit).pack(side="right", padx=5)

    def open_add_window(self):
        if not self.can_edit:
            return
        p = self.app.palette
        win = ctk.CTkToplevel(self)
        win.title("Добавление записи")
        win.geometry("640x560")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.configure(fg_color=p["bg"])
        entries = {}
        ctk.CTkLabel(win, text="Новая запись", text_color=p["text"], font=("Arial", 18, "bold")).pack(anchor="w", padx=16, pady=(16, 8))
        body = ctk.CTkFrame(win, fg_color=p["bg2"], border_color=p["border"], border_width=1)
        body.pack(fill="both", expand=True, padx=16, pady=8)
        for i, col in enumerate(self.columns):
            ctk.CTkLabel(body, text=self.labels[i], text_color=p["text"]).grid(row=i, column=0, sticky="w", padx=12, pady=8)
            e = ctk.CTkEntry(body, width=330)
            e.grid(row=i, column=1, sticky="ew", padx=12, pady=8)
            entries[col] = e
            if self.table == "materials":
                self.attach_suggestion_box(body, i, col, e)
            if self.table == "suppliers" and col == "phone":
                def phone_mask(_event=None, entry=e):
                    formatted = format_phone(entry.get())
                    entry.delete(0, "end")
                    entry.insert(0, formatted)
                    entry.icursor("end")
                e.bind("<FocusOut>", phone_mask)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, weight=0)

        def save_new():
            vals = self.prepare_values(entries)
            if self.table == "suppliers" and "phone" in self.columns:
                phone_index = self.columns.index("phone")
                vals[phone_index] = format_phone(vals[phone_index])
                if vals[phone_index] and not is_valid_phone(vals[phone_index]):
                    messagebox.showerror("Ошибка", "Номер телефона должен быть в формате +7(999)123-45-67")
                    return
            with db() as con:
                if self.duplicate_exists(con, vals):
                    messagebox.showwarning("Запись уже существует", self.duplicate_message())
                    return
                con.execute(f"INSERT INTO {self.table}({','.join(self.columns)}) VALUES({','.join('?' for _ in self.columns)})", vals)
            win.destroy()
            self.refresh()
            self.app.refresh_all()

        actions = ctk.CTkFrame(win, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=(4, 16))
        ctk.CTkButton(actions, text="Отмена", command=win.destroy).pack(side="right", padx=5)
        ctk.CTkButton(actions, text="Добавить", fg_color=p["red"], command=save_new).pack(side="right", padx=5)

    def add(self):
        if not self.validate():
            return
        vals = self.values()
        with db() as con:
            if self.duplicate_exists(con, vals):
                messagebox.showwarning("Запись уже существует", self.duplicate_message())
                return
            con.execute(f"INSERT INTO {self.table}({','.join(self.columns)}) VALUES({','.join('?' for _ in self.columns)})", vals)
        self.clear(); self.refresh(); self.app.refresh_all()

    def update(self):
        if not self.selected_id:
            return messagebox.showwarning("Выбор", "Выберите строку")
        self.open_edit_window()

    def delete(self):
        if not self.can_edit:
            return
        if not self.selected_id: return messagebox.showwarning("Выбор", "Выберите строку")
        if messagebox.askyesno("Удаление", "Удалить выбранную запись?"):
            with db() as con: con.execute(f"DELETE FROM {self.table} WHERE id=?", (self.selected_id,))
            self.clear(); self.refresh(); self.app.refresh_all()


class MovementTab(ExcelFilterMixin, ctk.CTkFrame):
    def __init__(self, master, app, kind):
        super().__init__(master, fg_color="transparent")
        self.app, self.kind = app, kind
        self.material_rows = []
        self.all_table_rows = []
        self.init_excel_filters()
        self.current_table_cols = []
        self.build()
        self.refresh()

    def build(self):
        p = self.app.palette
        top = ctk.CTkFrame(self, fg_color=p["bg2"])
        top.pack(fill="x", padx=12, pady=8)

        ctk.CTkLabel(top, text="Производитель", text_color=p["text"]).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 0))
        ctk.CTkLabel(top, text="Наименование изделия", text_color=p["text"]).grid(row=0, column=1, sticky="w", padx=8, pady=(8, 0))
        ctk.CTkLabel(top, text="Цвет", text_color=p["text"]).grid(row=0, column=2, sticky="w", padx=8, pady=(8, 0))

        self.manufacturer_box = ctk.CTkComboBox(top, width=250, values=[], command=self.on_manufacturer_change)
        self.manufacturer_box.set("")
        self.manufacturer_box.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="ew")
        self.item_box = ctk.CTkComboBox(top, width=250, values=[], command=self.on_item_change)
        self.item_box.set("")
        self.item_box.grid(row=1, column=1, padx=8, pady=(0, 8), sticky="ew")
        self.color_box = ctk.CTkComboBox(top, width=250, values=[])
        self.color_box.set("")
        self.color_box.grid(row=1, column=2, padx=8, pady=(0, 8), sticky="ew")

        self.qty = ctk.CTkEntry(top, placeholder_text="Количество")
        self.qty.grid(row=2, column=0, padx=8, pady=8, sticky="ew")
        self.note = ctk.CTkEntry(top, placeholder_text="Примечание", width=260)
        self.note.grid(row=2, column=1, padx=8, pady=8, sticky="ew")

        if self.kind == "receipts":
            self.price = ctk.CTkEntry(top, placeholder_text="Цена")
            self.price.grid(row=2, column=2, padx=8, pady=8, sticky="ew")
            text = "Добавить поступление"
        else:
            self.qty.configure(placeholder_text="Количество изделий")
            self.expense_item = ctk.CTkComboBox(top, values=list(EXPENSE_NORMS.keys()), command=self.update_expense_norm, width=260)
            self.expense_item.set("")
            self.expense_item.grid(row=3, column=0, padx=8, pady=8, sticky="ew")
            self.norm_label = ctk.CTkLabel(top, text="", text_color=p["text2"])
            self.norm_label.grid(row=3, column=1, padx=8, sticky="w")
            self.expense_item.set("Кухня прямая 3 метра")
            self.update_expense_norm("Кухня прямая 3 метра")
            text = "Списать расход"

        ctk.CTkButton(top, text=text, fg_color=p["red"], command=self.add).grid(row=4, column=0, padx=8, pady=8)

        self.tree = ttk.Treeview(self, show="headings", style="App.Treeview")
        self.tree.pack(fill="both", expand=True, padx=12, pady=8)

    def refresh_headings(self):
        if not hasattr(self, "tree"):
            return
        headings = getattr(self, "current_headings", {})
        for c in self.current_table_cols:
            title = headings.get(c, c)
            self.tree.heading(c, text=self.heading_text(title, c), command=lambda col=c, t=title: self.open_column_filter(col, t))

    def apply_filters(self):
        if not hasattr(self, "tree"):
            return
        self.tree.delete(*self.tree.get_children())
        for r in self.all_table_rows:
            if self.value_passes_column_filters(r):
                self.tree.insert("", "end", values=[r[c] for c in self.current_table_cols])

    def update_expense_norm(self, val):
        norm = EXPENSE_NORMS.get(val, 0)
        if hasattr(self, "norm_label"):
            self.norm_label.configure(text=f"Норма: {norm:g} лист(ов) на изделие")

    def duplicate_exists(self, con, vals, exclude_id=None):
        data = {c: (vals[i] if i < len(vals) else "") for i, c in enumerate(self.columns)}
        params = []
        where = []

        def norm(v):
            return (v or "").strip().lower()

        if self.table == "materials":
            check_cols = [c for c in ("material", "manufacturer", "color", "size", "thickness") if c in self.columns]
            if not check_cols:
                return False
            for c in check_cols:
                where.append(f"LOWER(TRIM(COALESCE({c},'')))=?")
                params.append(norm(data.get(c)))
        elif self.table == "suppliers":
            checks = []
            name = norm(data.get("name"))
            email = norm(data.get("email"))
            phone = norm(data.get("phone"))
            if name:
                checks.append("LOWER(TRIM(COALESCE(name,'')))=?")
                params.append(name)
            if email and email != "н/д":
                checks.append("LOWER(TRIM(COALESCE(email,'')))=?")
                params.append(email)
            if phone and phone != "н/д":
                checks.append("LOWER(TRIM(COALESCE(phone,'')))=?")
                params.append(phone)
            if not checks:
                return False
            where.append("(" + " OR ".join(checks) + ")")
        else:
            return False

        if exclude_id is not None:
            where.append("id<>?")
            params.append(exclude_id)
        sql = f"SELECT id FROM {self.table} WHERE " + " AND ".join(where) + " LIMIT 1"
        return con.execute(sql, params).fetchone() is not None

    def duplicate_message(self):
        if self.table == "materials":
            return "Материал с такими параметрами уже есть в базе данных."
        if self.table == "suppliers":
            return "Поставщик с такими данными уже есть в базе данных."
        return "Данная запись уже есть в базе данных."

    def refresh(self):
        with db() as con:
            self.material_rows = con.execute("SELECT id, material, manufacturer, color, color_code, quantity FROM materials ORDER BY manufacturer, material, color").fetchall()
        manufacturers = sorted({(r["manufacturer"] or "").strip() for r in self.material_rows if (r["manufacturer"] or "").strip()})
        self.manufacturer_box.configure(values=manufacturers)
        if manufacturers and self.manufacturer_box.get() not in manufacturers:
            self.manufacturer_box.set(manufacturers[0])
        self.on_manufacturer_change(self.manufacturer_box.get())
        self.reload_table()

    def on_manufacturer_change(self, val):
        items = sorted({(r["material"] or "").strip() for r in self.material_rows if (r["manufacturer"] or "").strip() == val and (r["material"] or "").strip()})
        self.item_box.configure(values=items)
        if items and self.item_box.get() not in items:
            self.item_box.set(items[0])
        elif not items:
            self.item_box.set("")
        self.on_item_change(self.item_box.get())

    def on_item_change(self, val):
        manufacturer = self.manufacturer_box.get()
        colors = sorted({(r["color"] or "").strip() for r in self.material_rows if (r["manufacturer"] or "").strip() == manufacturer and (r["material"] or "").strip() == val and (r["color"] or "").strip()})
        self.color_box.configure(values=colors)
        if colors and self.color_box.get() not in colors:
            self.color_box.set(colors[0])
        elif not colors:
            self.color_box.set("")

    def selected_material_id(self):
        manufacturer = self.manufacturer_box.get()
        material = self.item_box.get()
        color = self.color_box.get()
        for r in self.material_rows:
            if ((r["manufacturer"] or "").strip() == manufacturer and (r["material"] or "").strip() == material and (r["color"] or "").strip() == color):
                return r["id"]
        return None

    def reload_table(self):
        if self.kind == "receipts":
            cols = ["date", "manufacturer", "material", "color", "qty", "price", "note"]
            headings = {"date":"Дата","manufacturer":"Производитель","material":"Наименование","color":"Цвет","qty":"Кол-во","price":"Цена","note":"Примечание"}
        else:
            cols = ["date", "manufacturer", "material", "color", "items", "norm", "qty", "info", "note"]
            headings = {"date":"Дата","manufacturer":"Производитель","material":"Наименование","color":"Цвет","items":"Изделий","norm":"Листов/изд.","qty":"Списано листов","info":"Изделие","note":"Примечание"}
        self.current_table_cols = cols
        self.current_headings = headings
        # Удаляем фильтры по столбцам, которых больше нет после смены таблицы.
        self.column_filters = {c: v for c, v in self.column_filters.items() if c in cols}
        self.numeric_filters = {c: v for c, v in self.numeric_filters.items() if c in cols}
        self.tree.configure(columns=cols)
        for c in cols:
            self.tree.heading(c, text=self.heading_text(headings[c], c), command=lambda col=c, t=headings[c]: self.open_column_filter(col, t))
            self.tree.column(c, width=130)
        with db() as con:
            if self.kind == "receipts":
                rows = con.execute('''SELECT r.date,m.manufacturer,m.material,m.color,r.quantity qty,r.price price,r.note
                                      FROM receipts r LEFT JOIN materials m ON m.id=r.material_id ORDER BY r.id DESC''').fetchall()
            else:
                rows = con.execute('''SELECT e.date,m.manufacturer,m.material,m.color,e.item_count items,e.sheets_per_item norm,e.quantity qty,e.product_subtype info,e.note
                                      FROM expenses e LEFT JOIN materials m ON m.id=e.material_id ORDER BY e.id DESC''').fetchall()
        self.all_table_rows = rows
        self.apply_filters()

    def add(self):
        try:
            qty = float(self.qty.get().replace(',', '.'))
        except ValueError:
            return messagebox.showerror("Ошибка", "Введите корректное количество")
        mid = self.selected_material_id()
        if not mid:
            return messagebox.showwarning("Выбор материала", "Выберите производителя, наименование изделия и цвет")
        today = datetime.now().strftime("%Y-%m-%d %H:%M")
        with db() as con:
            if self.kind == "receipts":
                try:
                    price = float((self.price.get() or '0').replace(',', '.'))
                except ValueError:
                    return messagebox.showerror("Ошибка", "Введите корректную цену")
                duplicate = con.execute("""SELECT id FROM receipts
                                         WHERE date(date)=date(?) AND material_id=?
                                           AND ABS(COALESCE(quantity,0)-?)<0.000001
                                           AND ABS(COALESCE(price,0)-?)<0.000001
                                         LIMIT 1""", (today, mid, qty, price)).fetchone()
                if duplicate:
                    messagebox.showwarning("Запись уже существует", "Такое поступление уже зарегистрировано.")
                    return
                con.execute("INSERT INTO receipts(date,material_id,supplier_id,quantity,price,note) VALUES(?,?,?,?,?,?)", (today, mid, None, qty, price, self.note.get()))
                con.execute("UPDATE materials SET quantity=quantity+? WHERE id=?", (qty, mid))
            else:
                item_name = self.expense_item.get()
                norm = EXPENSE_NORMS.get(item_name, 0)
                sheets_total = qty * norm
                stock = con.execute("SELECT quantity FROM materials WHERE id=?", (mid,)).fetchone()[0] or 0
                if stock < sheets_total:
                    messagebox.showwarning("Недостаточно листов", f"На остатке {stock:g} лист(ов), требуется {sheets_total:g} лист(ов).\nРасход не списан. Сначала оформите поступление.")
                    return
                duplicate = con.execute("""SELECT id FROM expenses
                                         WHERE date(date)=date(?) AND material_id=? AND product_subtype=?
                                           AND ABS(COALESCE(item_count,0)-?)<0.000001
                                           AND ABS(COALESCE(quantity,0)-?)<0.000001
                                         LIMIT 1""", (today, mid, item_name, qty, sheets_total)).fetchone()
                if duplicate:
                    messagebox.showwarning("Запись уже существует", "Такой расход уже зарегистрирован.")
                    return
                con.execute("INSERT INTO expenses(date,material_id,product_type,product_subtype,quantity,note,item_count,sheets_per_item) VALUES(?,?,?,?,?,?,?,?)", (today, mid, "Изделие", item_name, sheets_total, self.note.get(), qty, norm))
                con.execute("UPDATE materials SET quantity=quantity-? WHERE id=?", (sheets_total, mid))
        self.qty.delete(0, "end")
        self.note.delete(0, "end")
        if self.kind == "receipts" and hasattr(self, "price"):
            self.price.delete(0, "end")
        self.reload_table()
        self.app.refresh_all()



class ReportsTab(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.current = "stock"
        self.report_title = ""
        self.report_headers = []
        self.report_rows = []
        self.filters = {
            "stock": {"material": "", "manufacturer": "Все", "size": "", "thickness": "", "stock_mode": "Все", "stock_n": ""},
            "receipts": {"date_mode": "Все", "date_year": "", "date_month": "", "date_year_from": "", "date_year_to": "", "date_month_from": "", "date_month_to": "", "manufacturer": "Все", "qty_mode": "Все", "qty_n": "", "price_mode": "Все", "price_n": ""},
            "expenses": {"date_mode": "Все", "date_year": "", "date_month": "", "date_year_from": "", "date_year_to": "", "date_month_from": "", "date_month_to": "", "manufacturer": "Все", "product": "Все", "items_mode": "Все", "items_n": "", "sheets_mode": "Все", "sheets_n": ""},
        }
        self.build()

    def build(self):
        p = self.app.palette
        top = ctk.CTkFrame(self, fg_color=p["bg2"], border_color=p["border"], border_width=1)
        top.pack(fill="x", padx=12, pady=8)

        ctk.CTkButton(top, text="Остатки материалов", fg_color=p["red"], command=lambda: self.show("stock")).pack(side="left", padx=6, pady=8)
        ctk.CTkButton(top, text="Поступления", fg_color=p["orange"], command=lambda: self.show("receipts")).pack(side="left", padx=6)
        ctk.CTkButton(top, text="Расходы", fg_color=p["orange"], command=lambda: self.show("expenses")).pack(side="left", padx=6)
        ctk.CTkButton(top, text="Фильтр", fg_color=p["red"], command=self.open_report_filter).pack(side="left", padx=16)
        ctk.CTkButton(top, text="Сбросить фильтр", fg_color=p["orange"], command=self.reset_filters).pack(side="left", padx=6)
        ctk.CTkButton(top, text="Экспорт в PDF", command=self.export_pdf).pack(side="right", padx=6)

        self.filter_info = ctk.CTkLabel(self, text="Фильтр: нет", text_color=p["text2"], anchor="w")
        self.filter_info.pack(fill="x", padx=16, pady=(0, 4))

        self.text = tk.Text(
            self, wrap="none", font=("Consolas", 10), bg=p["bg2"], fg=p["text"],
            insertbackground=p["text"], relief="flat", highlightthickness=1,
            highlightbackground=p["border"], state="disabled"
        )
        self.text.pack(fill="both", expand=True, padx=12, pady=8)
        self.show("stock")

    def show(self, kind):
        self.current = kind
        self.refresh_report()

    def get_manufacturers(self):
        with db() as con:
            return [r[0] for r in con.execute("SELECT DISTINCT manufacturer FROM materials WHERE COALESCE(manufacturer,'')<>'' ORDER BY manufacturer").fetchall()]

    def reset_filters(self):
        defaults = {
            "stock": {"material": "", "manufacturer": "Все", "size": "", "thickness": "", "stock_mode": "Все", "stock_n": ""},
            "receipts": {"date_mode": "Все", "date_year": "", "date_month": "", "date_year_from": "", "date_year_to": "", "date_month_from": "", "date_month_to": "", "manufacturer": "Все", "qty_mode": "Все", "qty_n": "", "price_mode": "Все", "price_n": ""},
            "expenses": {"date_mode": "Все", "date_year": "", "date_month": "", "date_year_from": "", "date_year_to": "", "date_month_from": "", "date_month_to": "", "manufacturer": "Все", "product": "Все", "items_mode": "Все", "items_n": "", "sheets_mode": "Все", "sheets_n": ""},
        }
        self.filters[self.current] = defaults[self.current]
        self.refresh_report()

    def open_report_filter(self):
        p = self.app.palette
        win = ctk.CTkToplevel(self)
        win.title("Фильтр отчета")
        win.geometry("520x420")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.configure(fg_color=p["bg"])

        title = {"stock": "Остатки", "receipts": "Поступление", "expenses": "Расходы"}[self.current]
        ctk.CTkLabel(win, text=f"Фильтр отчета: {title}", text_color=p["text"], font=("Arial", 17, "bold")).pack(anchor="w", padx=16, pady=(14, 10))
        form = ctk.CTkFrame(win, fg_color=p["bg2"], border_color=p["border"], border_width=1)
        form.pack(fill="both", expand=True, padx=16, pady=8)
        widgets = {}

        def label(row, text):
            ctk.CTkLabel(form, text=text, text_color=p["text"]).grid(row=row, column=0, sticky="w", padx=10, pady=7)

        def entry(row, key, placeholder=""):
            label(row, placeholder or key)
            e = ctk.CTkEntry(form, placeholder_text=placeholder)
            e.insert(0, self.filters[self.current].get(key, ""))
            e.grid(row=row, column=1, sticky="ew", padx=10, pady=7)
            widgets[key] = e

        def combo(row, key, text, values):
            label(row, text)
            cb = ctk.CTkComboBox(form, values=values)
            current = self.filters[self.current].get(key, values[0])
            cb.set(current if current in values else values[0])
            cb.grid(row=row, column=1, sticky="ew", padx=10, pady=7)
            widgets[key] = cb

        def date_filter(row):
            label(row, "Дата")
            box = ctk.CTkFrame(form, fg_color="transparent")
            box.grid(row=row, column=1, sticky="ew", padx=10, pady=7)
            modes = ["Все", "Год", "Месяц", "Диапазон годов", "Диапазон месяцев"]
            mode = ctk.CTkComboBox(box, values=modes, width=170)
            mode.set(self.filters[self.current].get("date_mode", "Все"))
            mode.grid(row=0, column=0, padx=2, pady=2, sticky="w")
            e1 = ctk.CTkEntry(box, placeholder_text="Год / от", width=92)
            e2 = ctk.CTkEntry(box, placeholder_text="Месяц / до", width=92)
            e3 = ctk.CTkEntry(box, placeholder_text="Год до", width=92)
            e1.grid(row=0, column=1, padx=2, pady=2)
            e2.grid(row=0, column=2, padx=2, pady=2)
            e3.grid(row=0, column=3, padx=2, pady=2)
            e1.insert(0, self.filters[self.current].get("date_year", "") or self.filters[self.current].get("date_year_from", "") or self.filters[self.current].get("date_month_from", ""))
            e2.insert(0, self.filters[self.current].get("date_month", "") or self.filters[self.current].get("date_month_to", ""))
            e3.insert(0, self.filters[self.current].get("date_year_to", ""))
            widgets["date_mode"] = mode
            widgets["date_entry_1"] = e1
            widgets["date_entry_2"] = e2
            widgets["date_entry_3"] = e3

        def ask_report_number(mode_key, n_key, mode_text, on_done=None):
            dlg = ctk.CTkToplevel(win)
            dlg.title(mode_text)
            dlg.geometry("320x180")
            dlg.transient(win)
            dlg.grab_set()
            dlg.configure(fg_color=p["bg"])
            ctk.CTkLabel(dlg, text=mode_text, text_color=p["text"], font=("Arial", 15, "bold")).pack(anchor="w", padx=16, pady=(16, 8))
            e = ctk.CTkEntry(dlg, placeholder_text="Введите число")
            current_n = self.filters[self.current].get(n_key, "")
            if current_n:
                e.insert(0, current_n)
            e.pack(fill="x", padx=16, pady=(0, 12))

            def apply_number():
                raw = e.get().strip()
                try:
                    float(raw.replace(',', '.'))
                except ValueError:
                    messagebox.showerror("Ошибка", "Введите корректное число")
                    return
                self.filters[self.current][mode_key] = mode_text
                self.filters[self.current][n_key] = raw
                dlg.destroy()
                if on_done:
                    on_done()

            actions = ctk.CTkFrame(dlg, fg_color="transparent")
            actions.pack(fill="x", padx=16, pady=(0, 14))
            ctk.CTkButton(actions, text="Отмена", fg_color=p["orange"], command=dlg.destroy).pack(side="left", padx=4)
            ctk.CTkButton(actions, text="Применить", fg_color=p["red"], command=apply_number).pack(side="right", padx=4)
            e.bind("<Return>", lambda _ev: apply_number())
            e.focus_set()

        def numeric_pair(row, mode_key, n_key, text):
            label(row, text)
            box = ctk.CTkFrame(form, fg_color="transparent")
            box.grid(row=row, column=1, sticky="ew", padx=10, pady=7)

            status = ctk.CTkLabel(box, text_color=p["text2"], anchor="w")
            def update_status():
                mode = self.filters[self.current].get(mode_key, "Все")
                n = self.filters[self.current].get(n_key, "")
                if mode in ("Больше...", "Меньше...") and n:
                    status.configure(text=f"{mode} {n}")
                else:
                    status.configure(text=mode)

            def set_mode(mode, n=""):
                self.filters[self.current][mode_key] = mode
                self.filters[self.current][n_key] = n
                update_status()

            ctk.CTkButton(box, text="Все", width=56, command=lambda: set_mode("Все", "")).pack(side="left", padx=2)
            ctk.CTkButton(box, text="= 0", width=56, command=lambda: set_mode("= 0", "")).pack(side="left", padx=2)
            ctk.CTkButton(box, text="≠ 0", width=56, command=lambda: set_mode("≠ 0", "")).pack(side="left", padx=2)
            ctk.CTkButton(box, text="Больше...", width=88, fg_color=p["orange"], command=lambda: ask_report_number(mode_key, n_key, "Больше...", update_status)).pack(side="left", padx=2)
            ctk.CTkButton(box, text="Меньше...", width=88, fg_color=p["orange"], command=lambda: ask_report_number(mode_key, n_key, "Меньше...", update_status)).pack(side="left", padx=2)
            status.pack(side="left", padx=(8, 0), fill="x", expand=True)
            update_status()

        manufacturers = ["Все"] + self.get_manufacturers()
        if self.current == "stock":
            entry(0, "material", "Материал")
            combo(1, "manufacturer", "Производитель", manufacturers)
            entry(2, "size", "Размер")
            entry(3, "thickness", "Толщина")
            numeric_pair(4, "stock_mode", "stock_n", "Остаток")
        elif self.current == "receipts":
            date_filter(0)
            combo(1, "manufacturer", "Производитель", manufacturers)
            numeric_pair(2, "qty_mode", "qty_n", "Кол-во")
            numeric_pair(3, "price_mode", "price_n", "Цена")
        else:
            date_filter(0)
            combo(1, "manufacturer", "Производитель", manufacturers)
            combo(2, "product", "Изделие", ["Все"] + list(EXPENSE_NORMS.keys()))
            numeric_pair(3, "items_mode", "items_n", "Кол-во изделий")
            numeric_pair(4, "sheets_mode", "sheets_n", "Списано листов")

        form.grid_columnconfigure(1, weight=1)

        def apply():
            for key, widget in widgets.items():
                if key.startswith("date_entry_"):
                    continue
                self.filters[self.current][key] = widget.get().strip()
            if "date_mode" in widgets:
                mode = widgets["date_mode"].get().strip()
                v1 = widgets["date_entry_1"].get().strip()
                v2 = widgets["date_entry_2"].get().strip()
                v3 = widgets["date_entry_3"].get().strip()
                fcur = self.filters[self.current]
                for k in ("date_year", "date_month", "date_year_from", "date_year_to", "date_month_from", "date_month_to"):
                    fcur[k] = ""
                if mode == "Год":
                    fcur["date_year"] = v1
                elif mode == "Месяц":
                    fcur["date_year"] = v1
                    fcur["date_month"] = v2
                elif mode == "Диапазон годов":
                    fcur["date_year_from"] = v1
                    fcur["date_year_to"] = v3 or v2
                elif mode == "Диапазон месяцев":
                    fcur["date_year"] = v1
                    fcur["date_month_from"] = v2
                    fcur["date_month_to"] = v3
            win.destroy()
            self.refresh_report()

        def reset_window():
            win.destroy()
            self.reset_filters()

        actions = ctk.CTkFrame(win, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(actions, text="Сбросить", fg_color=p["orange"], command=reset_window).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="Применить", fg_color=p["red"], command=apply).pack(side="right", padx=4)

    def number_passes(self, value, mode, raw_n):
        if mode in ("", "Все", None):
            return True
        try:
            num = float(value or 0)
        except Exception:
            num = 0.0
        if mode == "= 0":
            return num == 0
        if mode == "≠ 0":
            return num != 0
        try:
            n = float(str(raw_n).replace(',', '.'))
        except Exception:
            return True
        if mode == "Больше...":
            return num > n
        if mode == "Меньше...":
            return num < n
        return True

    def contains_filter(self, value, needle):
        needle = (needle or "").strip().lower()
        if not needle:
            return True
        return needle in as_cell_text(value).lower()

    def parse_date_parts(self, value):
        text = as_cell_text(value).strip()
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"):
            try:
                d = datetime.strptime(text[:10], fmt)
                return d.year, d.month
            except Exception:
                pass
        m = re.search(r"(20\d{2}|19\d{2})[-./](\d{1,2})", text)
        if m:
            return int(m.group(1)), int(m.group(2))
        return None, None

    def date_passes(self, value, f):
        mode = f.get("date_mode", "Все")
        if mode in ("", "Все", None):
            return True
        year, month = self.parse_date_parts(value)
        if not year:
            return False
        try:
            if mode == "Год":
                return year == int(f.get("date_year") or 0)
            if mode == "Месяц":
                y = f.get("date_year", "").strip()
                m = int(f.get("date_month") or 0)
                return (not y or year == int(y)) and month == m
            if mode == "Диапазон годов":
                y1 = int(f.get("date_year_from") or 0)
                y2 = int(f.get("date_year_to") or 9999)
                return y1 <= year <= y2
            if mode == "Диапазон месяцев":
                y = f.get("date_year", "").strip()
                m1 = int(f.get("date_month_from") or 1)
                m2 = int(f.get("date_month_to") or 12)
                return (not y or year == int(y)) and m1 <= month <= m2
        except ValueError:
            return True
        return True

    def update_filter_info(self):
        f = self.filters.get(self.current, {})
        parts = []
        names = {
            "material": "материал", "manufacturer": "производитель", "size": "размер", "thickness": "толщина",
            "date": "дата", "date_mode": "дата", "product": "изделие", "stock_mode": "остаток", "qty_mode": "кол-во",
            "price_mode": "цена", "items_mode": "кол-во изделий", "sheets_mode": "списано листов"
        }
        for key, value in f.items():
            if key.endswith("_n") or key in ("date_year", "date_month", "date_year_from", "date_year_to", "date_month_from", "date_month_to"):
                continue
            if value and value != "Все":
                suffix = ""
                n_key = key.replace("_mode", "_n")
                if key.endswith("_mode") and value in ("Больше...", "Меньше...") and f.get(n_key):
                    suffix = f" {f.get(n_key)}"
                parts.append(f"{names.get(key, key)}: {value}{suffix}")
        self.filter_info.configure(text="Фильтр: " + ("; ".join(parts) if parts else "нет"))

    def refresh_report(self):
        f = self.filters.get(self.current, {})
        with db() as con:
            if self.current == "stock":
                title = "ОТЧЕТ ПО ОСТАТКАМ МАТЕРИАЛОВ"
                rows = con.execute("SELECT material,manufacturer,color,color_code,size,thickness,quantity FROM materials ORDER BY material,manufacturer,color").fetchall()
                header = ["Материал", "Производитель", "Цвет", "Артикул", "Размер", "Толщина", "Остаток"]
                filtered = []
                for r in rows:
                    if not self.contains_filter(r[0], f.get("material")): continue
                    if f.get("manufacturer", "Все") != "Все" and (r[1] or "") != f.get("manufacturer"): continue
                    if not self.contains_filter(r[4], f.get("size")): continue
                    if not self.contains_filter(r[5], f.get("thickness")): continue
                    if not self.number_passes(r[6], f.get("stock_mode"), f.get("stock_n")): continue
                    filtered.append([as_cell_text(x) for x in r])
            elif self.current == "receipts":
                title = "ОТЧЕТ ПО ПОСТУПЛЕНИЯМ"
                rows = con.execute("SELECT r.date,m.manufacturer,m.material,m.color,r.quantity,r.price,r.note FROM receipts r LEFT JOIN materials m ON m.id=r.material_id ORDER BY r.id DESC").fetchall()
                header = ["Дата", "Производитель", "Наименование", "Цвет", "Кол-во", "Цена", "Примечание"]
                filtered = []
                for r in rows:
                    if not self.date_passes(r[0], f): continue
                    if f.get("manufacturer", "Все") != "Все" and (r[1] or "") != f.get("manufacturer"): continue
                    if not self.number_passes(r[4], f.get("qty_mode"), f.get("qty_n")): continue
                    if not self.number_passes(r[5], f.get("price_mode"), f.get("price_n")): continue
                    filtered.append([as_cell_text(x) for x in r])
            else:
                title = "ОТЧЕТ ПО РАСХОДАМ"
                rows = con.execute("SELECT e.date,m.manufacturer,m.material,m.color,e.product_subtype,e.item_count,e.sheets_per_item,e.quantity,e.note FROM expenses e LEFT JOIN materials m ON m.id=e.material_id ORDER BY e.id DESC").fetchall()
                header = ["Дата", "Производитель", "Наименование", "Цвет", "Изделие", "Кол-во изделий", "Листов/изд.", "Списано листов", "Примечание"]
                filtered = []
                for r in rows:
                    if not self.date_passes(r[0], f): continue
                    if f.get("manufacturer", "Все") != "Все" and (r[1] or "") != f.get("manufacturer"): continue
                    if f.get("product", "Все") != "Все" and (r[4] or "") != f.get("product"): continue
                    if not self.number_passes(r[5], f.get("items_mode"), f.get("items_n")): continue
                    if not self.number_passes(r[7], f.get("sheets_mode"), f.get("sheets_n")): continue
                    filtered.append([as_cell_text(x) for x in r])

        self.report_title = title
        self.report_headers = header
        self.report_rows = filtered
        self.update_filter_info()
        self.render_report_text()

    def render_report_text(self):
        lines = [
            self.report_title,
            f"ООО 'Мебельное ателье', г. Киров | {datetime.now():%d.%m.%Y %H:%M}",
            f"Записей: {len(self.report_rows)}",
            "",
        ]
        lines.extend(self.make_text_table(self.report_headers, self.report_rows))
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", "\n".join(lines))
        self.text.configure(state="disabled")

    def make_text_table(self, headers, rows):
        max_width = 28
        prepared = [[str(c) for c in headers]] + [[str(c) for c in row] for row in rows]
        widths = []
        for i in range(len(headers)):
            width = max(len(r[i]) if i < len(r) else 0 for r in prepared) if prepared else len(headers[i])
            widths.append(min(max(width, len(headers[i]), 6), max_width))

        def crop(text, width):
            text = str(text)
            return text if len(text) <= width else text[:max(0, width - 1)] + "…"

        def border(left, mid, right):
            return left + mid.join("─" * (w + 2) for w in widths) + right

        def row_line(values):
            cells = []
            for i, w in enumerate(widths):
                value = crop(values[i] if i < len(values) else "", w)
                cells.append(" " + value.ljust(w) + " ")
            return "│" + "│".join(cells) + "│"

        table = [border("┌", "┬", "┐"), row_line(headers), border("├", "┼", "┤")]
        for row in rows:
            table.append(row_line(row))
        table.append(border("└", "┴", "┘"))
        return table

    def export_pdf(self):
        if not self.report_headers:
            self.refresh_report()
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"report_{self.current}.pdf"
        )
        if not path:
            return
        try:
            self.save_table_as_pdf(path)
            messagebox.showinfo("Отчет", f"PDF-файл сохранен:\n{path}")
        except Exception as exc:
            messagebox.showerror("Ошибка", f"Не удалось сохранить PDF:\n{exc}")

    def find_pdf_font(self):
        candidates = [
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\calibri.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
        for item in candidates:
            if os.path.exists(item):
                return item
        return None

    def save_table_as_pdf(self, path):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

        font_name = "Helvetica"
        font_path = self.find_pdf_font()
        if font_path:
            try:
                pdfmetrics.registerFont(TTFont("AppFont", font_path))
                font_name = "AppFont"
            except Exception:
                pass

        doc = SimpleDocTemplate(path, pagesize=landscape(A4), rightMargin=10*mm, leftMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)
        styles = getSampleStyleSheet()
        styles["Title"].fontName = font_name
        styles["Normal"].fontName = font_name
        story = [
            Paragraph(self.report_title, styles["Title"]),
            Paragraph(f"ООО 'Мебельное ателье', г. Киров | {datetime.now():%d.%m.%Y %H:%M} | Записей: {len(self.report_rows)}", styles["Normal"]),
            Spacer(1, 6),
        ]
        data = [self.report_headers] + self.report_rows
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E53935")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FFF8F3")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
            ("TOPPADDING", (0, 0), (-1, 0), 7),
        ]))
        story.append(table)
        doc.build(story)


class Login(ctk.CTk):
    def __init__(self):
        super().__init__(); self.authenticated=False; self.title("Вход — Мебельное ателье"); self.geometry("420x320"); ctk.set_appearance_mode("light")
        try:
            self._window_icon = tk.PhotoImage(file=str(LOGO_PATH))
            self.iconphoto(True, self._window_icon)
        except Exception:
            pass
        frame=ctk.CTkFrame(self); frame.pack(expand=True, fill="both", padx=30, pady=30)
        ctk.CTkLabel(frame, text="ООО \"Мебельное ателье\"", font=("Arial",22,"bold")).pack(pady=20)
        self.login=ctk.CTkEntry(frame, placeholder_text="Логин"); self.login.pack(pady=8)
        self.password=ctk.CTkEntry(frame, placeholder_text="Пароль", show="*"); self.password.pack(pady=8)
        ctk.CTkButton(frame, text="Войти", fg_color=LIGHT["red"], command=self.auth).pack(pady=16)
    def auth(self):
        with db() as con:
            row = con.execute("SELECT role FROM users WHERE login=? AND password=?", (self.login.get(), self.password.get())).fetchone()
        if row:
            # Не создаем новое окно внутри обработчика кнопки: сначала корректно
            # останавливаем окно входа, чтобы CustomTkinter успел отменить after-callbacks.
            self.authenticated = True
            self.user_role = row["role"] or ROLE_EMPLOYEE
            self.withdraw()
            self.after(50, self.quit)
        else:
            messagebox.showerror("Ошибка", "Неверный логин или пароль")


class App(ctk.CTk):
    def __init__(self, user_role=ROLE_ADMIN):
        super().__init__()
        self.user_role = user_role
        self.dark = False
        self.palette = LIGHT
        self.title("Учет товаров — ООО 'Мебельное ателье', г. Киров")
        self.set_window_icon()
        self.geometry("1500x850")
        self.resizable(False, False)
        self.bind("<F11>", self.toggle_fullscreen)
        self.bind("<Escape>", self.exit_fullscreen)
        self.tabs = {}
        self.page_frames = {}
        self.current_page = "materials"
        self.build()

    def set_window_icon(self):
        try:
            self._window_icon = tk.PhotoImage(file=str(LOGO_PATH))
            self.iconphoto(True, self._window_icon)
        except Exception:
            pass

    def toggle_fullscreen(self, _event=None):
        self.attributes("-fullscreen", not bool(self.attributes("-fullscreen")))

    def exit_fullscreen(self, _event=None):
        self.attributes("-fullscreen", False)

    def build(self):
        p = self.palette
        ctk.set_appearance_mode("dark" if self.dark else "light")
        self.configure(fg_color=p["bg"])
        apply_tree_style(p)

        root = ctk.CTkFrame(self, fg_color=p["bg"])
        root.pack(fill="both", expand=True)

        sidebar = ctk.CTkFrame(root, fg_color=p["bg2"], width=285, corner_radius=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        header = ctk.CTkFrame(sidebar, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(14, 10))
        try:
            from PIL import Image
            logo = ctk.CTkImage(Image.open(LOGO_PATH), size=(82, 82))
            ctk.CTkLabel(header, image=logo, text="").pack(pady=(0, 8))
        except Exception:
            pass
        ctk.CTkLabel(
            header,
            text='ООО "Мебельное ателье"\nг. Киров',
            font=("Arial", 18, "bold"),
            text_color=p["text"],
            justify="center"
        ).pack()
        role_text = "Администратор" if self.user_role == ROLE_ADMIN else "Сотрудник"
        ctk.CTkLabel(header, text=f"Роль: {role_text}", text_color=p["text2"]).pack(pady=(6, 0))

        self.theme_icon = None
        try:
            from PIL import Image
            icon_path = ICON_DARK_PATH if self.dark else ICON_LIGHT_PATH
            self.theme_icon = ctk.CTkImage(Image.open(icon_path), size=(26, 26))
        except Exception:
            pass
        ctk.CTkButton(
            sidebar, text="", image=self.theme_icon, width=46, height=46,
            corner_radius=8, fg_color=p["bg"], hover_color=p["border"],
            border_width=1, border_color=p["border"], command=self.toggle_theme
        ).pack(pady=(0, 14))

        nav = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav.pack(fill="x", padx=12, pady=6)
        self.nav_buttons = {}
        pages = [
            ("materials", "Материалы"),
            ("suppliers", "Поставщики"),
            ("receipts", "Поступление"),
            ("expenses", "Расход"),
            ("reports", "Отчеты"),
        ]
        for key, title in pages:
            btn = ctk.CTkButton(
                nav, text=title, anchor="w", height=42,
                fg_color=p["red"] if key == self.current_page else "transparent",
                text_color="#FFFFFF" if key == self.current_page else p["text"],
                hover_color=p["orange"],
                command=lambda k=key: self.show_page(k)
            )
            btn.pack(fill="x", pady=4)
            self.nav_buttons[key] = btn

        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=12, pady=14)
        ctk.CTkButton(bottom, text="Выйти из профиля", fg_color=p["orange"], command=self.logout).pack(fill="x", pady=4)
        ctk.CTkButton(bottom, text="Закрыть программу", fg_color=p["red"], command=self.destroy).pack(fill="x", pady=4)

        self.content = ctk.CTkFrame(root, fg_color=p["bg"])
        self.content.pack(side="left", fill="both", expand=True)

        self.page_frames = {key: ctk.CTkFrame(self.content, fg_color="transparent") for key, _ in pages}
        self.tabs["materials"] = CRUDTab(self.page_frames["materials"], self, "materials", ["material","manufacturer","color","color_code","size","thickness","quantity","note"], ["Материал","Производитель","Цвет","Артикул","Размер","Толщина","Остаток","Примечание"])
        self.tabs["suppliers"] = CRUDTab(self.page_frames["suppliers"], self, "suppliers", ["name","phone","email","address","note"], ["Название","Телефон","Email","Адрес","Примечание"])
        self.tabs["receipts"] = MovementTab(self.page_frames["receipts"], self, "receipts")
        self.tabs["expenses"] = MovementTab(self.page_frames["expenses"], self, "expenses")
        self.tabs["reports"] = ReportsTab(self.page_frames["reports"], self)
        for key, widget in self.tabs.items():
            widget.pack(fill="both", expand=True)
        self.show_page(self.current_page)

    def show_page(self, key):
        self.current_page = key
        for frame in self.page_frames.values():
            frame.pack_forget()
        if key in self.page_frames:
            self.page_frames[key].pack(fill="both", expand=True)
        p = self.palette
        for name, btn in getattr(self, "nav_buttons", {}).items():
            active = name == key
            btn.configure(
                fg_color=p["red"] if active else "transparent",
                text_color="#FFFFFF" if active else p["text"]
            )

    def logout(self):
        if messagebox.askyesno("Выход", "Выйти из профиля?"):
            self.destroy()
            login = Login()
            login.mainloop()
            authenticated = getattr(login, "authenticated", False)
            try:
                login.destroy()
            except tk.TclError:
                pass
            if authenticated:
                App(getattr(login, "user_role", ROLE_EMPLOYEE)).mainloop()

    def toggle_theme(self):
        self.dark = not self.dark
        self.palette = DARK if self.dark else LIGHT
        for w in self.winfo_children():
            w.destroy()
        self.build()

    def refresh_all(self):
        for t in self.tabs.values():
            if hasattr(t, "refresh"):
                t.refresh()
        if "reports" in self.tabs:
            self.tabs["reports"].show("stock")

if __name__ == "__main__":
    init_db()
    login = Login()
    login.mainloop()
    authenticated = getattr(login, "authenticated", False)
    try:
        login.destroy()
    except tk.TclError:
        pass
    if authenticated:
        App(getattr(login, "user_role", ROLE_EMPLOYEE)).mainloop()
