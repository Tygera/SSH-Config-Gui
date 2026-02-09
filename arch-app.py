import os
import subprocess
import sys
import signal
from dataclasses import dataclass, field
from pathlib import Path
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext, font, simpledialog
except ImportError as exc:
    message = (
        "Tkinter is not available. On Arch Linux install it with:\n"
        "  sudo pacman -S tk\n\n"
        "If you are using a custom Python (pyenv, conda, self-built), you may need to rebuild Python after installing tk.\n\n"
        f"Original error: {exc}"
    )
    print(message, file=sys.stderr)
    raise SystemExit(1)
from typing import Optional
import hashlib
import json
from datetime import datetime


# ============================================================================
# COLORS
# ============================================================================
class ColorScheme:
    """Zentrale Farbdefinitionen für die gesamte UI"""
    
    # Hauptfarben
    PRIMARY = '#052342'           # Dunkelblau
    PRIMARY_LIGHT = '#0d3a5f'     # Helleres Blau
    SECONDARY = '#6c757d'         # Grau
    SUCCESS = '#28a745'           # Grün
    DANGER = '#dc3545'            # Rot
    WARNING = '#ffc107'           # Gelb
    INFO = '#17a2b8'              # Türkis
    
    # Hintergrundfarben
    BG_MAIN = '#f5f7fa'           # Haupthintergrund
    BG_WHITE = '#ffffff'          # Weiß
    BG_LIGHT = '#f8f9fa'          # Hellgrau
    BG_DARK = '#343a40'           # Dunkelgrau
    
    # Listen-Farben (für Treeview)
    LIST_ODD = '#ffffff'          # Ungerade Zeilen
    LIST_EVEN = '#e0e4e8'         # Gerade Zeilen
    LIST_SELECTED = '#cce5ff'     # Ausgewählt
    LIST_HOVER = '#e3f2fd'        # Hover
    
    # Text-Farben
    TEXT_PRIMARY = '#1a1a1a'      # Haupttext
    TEXT_SECONDARY = '#666666'    # Sekundärtext
    TEXT_LIGHT = '#999999'        # Heller Text
    TEXT_WHITE = '#ffffff'        # Weißer Text
    
    # Rahmen
    BORDER = '#d0d7de'            # Standard-Rahmen
    
    # Status
    STATUS_BG = '#0d3a5f'         # Statusleiste Hintergrund
    STATUS_TEXT = '#ffffff'       # Statusleiste Text


# ============================================================================
# PADDING
# ============================================================================
class Padding:
    FRAME = 10
    BUTTON = 6
    INPUT = 3

def getFirstAvailableFontFamily(preferred_families: list[str]) -> str:
    """Returns the first installed font family from a preference list."""
    try:
        available = set(font.families())
    except Exception:
        return ""

    for family in preferred_families:
        if family in available:
            return family

    return ""

def installSigintHandler(root: tk.Tk) -> None:
    def handleSigint(signum, frame):
        # Schedule GUI-safe work on the Tk event loop
        def onGuiThread():
            # Choose what you want:
            # 1) Ignore silently:
            # return

            # 2) Ask user:
            if messagebox.askyesno("Exit", "Ctrl+C received. Quit the application?"):
                root.destroy()

        root.after(0, onGuiThread)

    signal.signal(signal.SIGINT, handleSigint)


@dataclass
class SshHostEntry:
    host_alias: str
    options: dict[str, str] = field(default_factory=dict)

    def getDisplayLine(self) -> str:
        host_name = self.options.get("hostname", "")
        user_name = self.options.get("user", "")
        port = self.options.get("port", "")
        left = self.host_alias

        right_parts = []
        if user_name and host_name:
            right_parts.append(f"{user_name}@{host_name}")
        elif host_name:
            right_parts.append(host_name)
        if port:
            right_parts.append(f":{port}")

        right = "".join(right_parts) if right_parts else "(kein Hostname)"
        return f"{left}  ({right})"


class SshConfigParser:
    def parseFile(self, config_path: Path) -> list[SshHostEntry]:
        if not config_path.exists():
            return []

        entries: list[SshHostEntry] = []
        current_entry: Optional[SshHostEntry] = None

        try:
            for raw_line in config_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                if line.lower().startswith("host "):
                    if current_entry is not None:
                        entries.append(current_entry)

                    host_aliases = line.split(maxsplit=1)[1].strip()
                    first_token = host_aliases.split()[0]
                    current_entry = SshHostEntry(host_alias=first_token, options={})
                    continue

                if current_entry is None:
                    continue

                parts = line.split(None, 1)
                if len(parts) != 2:
                    continue

                key = parts[0].strip().lower()
                value = parts[1].strip().strip('"')
                current_entry.options[key] = value

            if current_entry is not None:
                entries.append(current_entry)

        except Exception as e:
            print(f"Fehler beim Parsen der SSH-Konfiguration: {e}")

        filtered = []
        for entry in entries:
            if any(ch in entry.host_alias for ch in ["*", "?", "!"]):
                continue
            filtered.append(entry)

        return filtered


class KeyGenerationDialog(tk.Toplevel):
    """Dialog für SSH-Schlüsselgenerierung mit Optionen"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.title("SSH-Schlüssel generieren")
        self.geometry("500x320")
        self.resizable(False, False)
        
        self.result = None
        
        # Modal machen
        self.transient(parent)
        self.grab_set()
        
        self.buildUi()
        
        # Zentrieren
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")
    
    def buildUi(self):
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Titel
        title = ttk.Label(main_frame, text="🔐 Neuen SSH-Schlüssel generieren", 
                         font=('Segoe UI', 12, 'bold'))
        title.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # Schlüssel-Typ
        ttk.Label(main_frame, text="Schlüssel-Typ:").grid(row=1, column=0, sticky="w", pady=5)
        self.key_type_var = tk.StringVar(value="ed25519")
        key_type_frame = ttk.Frame(main_frame)
        key_type_frame.grid(row=1, column=1, sticky="ew", pady=5)
        
        ttk.Radiobutton(key_type_frame, text="ed25519 (empfohlen)", 
                       variable=self.key_type_var, value="ed25519").pack(anchor="w")
        ttk.Radiobutton(key_type_frame, text="ecdsa", 
                       variable=self.key_type_var, value="ecdsa").pack(anchor="w")
        ttk.Radiobutton(key_type_frame, text="rsa (4096 bit)", 
                       variable=self.key_type_var, value="rsa").pack(anchor="w")
        
        # Alias/Name
        ttk.Label(main_frame, text="Schlüssel-Name:").grid(row=2, column=0, sticky="w", pady=5)
        self.key_name_var = tk.StringVar(value="")
        name_entry = ttk.Entry(main_frame, textvariable=self.key_name_var, width=30)
        name_entry.grid(row=2, column=1, sticky="ew", pady=5)
        name_entry.focus()
        
        hint = ttk.Label(main_frame, text="(Optional: z.B. 'work', 'personal', 'server1')", 
                        font=('Segoe UI', 8), foreground=ColorScheme.TEXT_SECONDARY)
        hint.grid(row=3, column=1, sticky="w", pady=(0, 10))
        
        # SSH-Config aktualisieren
        self.update_config_var = tk.BooleanVar(value=False)
        update_check = ttk.Checkbutton(main_frame, 
                                       text="Schlüssel zur SSH-Config hinzufügen",
                                       variable=self.update_config_var)
        update_check.grid(row=4, column=0, columnspan=2, sticky="w", pady=10)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, columnspan=2, pady=(20, 0))
        
        ttk.Button(button_frame, text="✓ Generieren", 
                  command=self.onGenerate, style="Primary.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="✗ Abbrechen", 
                  command=self.onCancel).pack(side=tk.LEFT, padx=5)
        
        main_frame.columnconfigure(1, weight=1)
    
    def onGenerate(self):
        key_type = self.key_type_var.get()
        key_name = self.key_name_var.get().strip()
        update_config = self.update_config_var.get()
        
        self.result = {
            'key_type': key_type,
            'key_name': key_name,
            'update_config': update_config
        }
        self.destroy()
    
    def onCancel(self):
        self.result = None
        self.destroy()


class SshGui(tk.Tk):
    # Label Konfiguration für die Details-Ansicht
    DETAIL_LABELS = {
        "host_alias": "🏷 Host-Alias",
        "hostname": "🌐 Hostname",
        "user": "👤 Benutzer",
        "port": "🔌 Port",
        "identityfile": "🔑 Identity-Datei"
    }

    def __init__(self) -> None:
        super().__init__()
        self.title("SSH Verwaltung")
        self.geometry("1100x650")
        self.minsize(900, 550)

        self.config_path = Path.home() / ".ssh" / "config"
        self.ssh_dir_path = Path.home() / ".ssh"
        self.notes_dir_path = self.ssh_dir_path / "notes"
        self.session_logs_dir_path = self.ssh_dir_path / "session_logs"
        self.putty_path = self.findPuttyPath()

        # Notes- und Session-Logs-Verzeichnis erstellen
        self.notes_dir_path.mkdir(parents=True, exist_ok=True)
        self.session_logs_dir_path.mkdir(parents=True, exist_ok=True)

        self.entries: list[SshHostEntry] = []
        self.selected_entry: Optional[SshHostEntry] = None

        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *args: self.filterEntries())

        self.buildUi()
        self.applyStyles()
        self.loadEntries()

    def buildUi(self) -> None:
        root_frame = ttk.Frame(self, padding=Padding.FRAME)
        root_frame.pack(fill=tk.BOTH, expand=True)

        root_frame.columnconfigure(0, weight=1)
        root_frame.columnconfigure(1, weight=2)
        root_frame.rowconfigure(0, weight=1)

        # Links: Liste
        left_frame = ttk.LabelFrame(root_frame, text="🖥️ Hosts", padding=Padding.FRAME)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left_frame.rowconfigure(2, weight=1)
        left_frame.columnconfigure(0, weight=1)

        # Pfad-Zeile
        path_row = ttk.Frame(left_frame)
        path_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        path_row.columnconfigure(1, weight=1)

        ttk.Label(path_row, text="📁 .ssh/config:").grid(row=0, column=0, sticky="w")
        self.label_config_path = ttk.Label(path_row, text=str(self.config_path), foreground=ColorScheme.PRIMARY)
        self.label_config_path.grid(row=0, column=1, sticky="w", padx=(8, 0))

        # Suchfeld
        search_row = ttk.Frame(left_frame)
        search_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        search_row.columnconfigure(1, weight=1)

        ttk.Label(search_row, text="🔍 Suche:").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        # Treeview
        self.tree = ttk.Treeview(left_frame, columns=("display",), show="headings", 
                                  selectmode="browse", style="Custom.Treeview")
        self.tree.heading("display", text="Host (Info)")
        self.tree.grid(row=2, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.bind("<Double-Button-1>", lambda e: self.connectNativeSsh())
        self.tree.bind("<<TreeviewSelect>>", self.onSelectEntry)

        # Buttons unten
        bottom_row = ttk.Frame(left_frame)
        bottom_row.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        bottom_row.columnconfigure(3, weight=1)

        ttk.Button(bottom_row, text="🔄 Neu laden", command=self.loadEntries, 
                   style="Action.TButton").grid(row=0, column=0, sticky="w")
        ttk.Button(bottom_row, text="📂 .ssh Ordner", command=self.openSshFolder,
                   style="Action.TButton").grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(bottom_row, text="📋 Logs", command=self.openSessionLogs,
                   style="Action.TButton").grid(row=0, column=2, sticky="w", padx=(8, 0))

        # Rechts: Details und Notizen
        right_frame = ttk.Frame(root_frame)
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.rowconfigure(1, weight=1)
        right_frame.columnconfigure(0, weight=1)

        # Details Frame
        details_frame = ttk.LabelFrame(right_frame, text="ℹ️ Details", padding=Padding.FRAME)
        details_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        details_frame.columnconfigure(1, weight=1)

        self.detail_vars: dict[str, tk.StringVar] = {}
        
        for row_index, (field_name, label_text) in enumerate(self.DETAIL_LABELS.items()):
            ttk.Label(details_frame, text=label_text + ":").grid(row=row_index, column=0, sticky="w", pady=Padding.INPUT)
            var = tk.StringVar(value="")
            self.detail_vars[field_name] = var
            entry = ttk.Entry(details_frame, textvariable=var, state="readonly", style="Readonly.TEntry")
            entry.grid(row=row_index, column=1, sticky="ew", pady=Padding.INPUT, padx=(8, 0))

        # Notizen Frame
        notes_frame = ttk.LabelFrame(right_frame, text="📝 Notizen (persistent)", padding=Padding.FRAME)
        notes_frame.grid(row=1, column=0, sticky="nsew")
        notes_frame.rowconfigure(0, weight=1)
        notes_frame.columnconfigure(0, weight=1)

        self.notes_text = scrolledtext.ScrolledText(notes_frame, wrap=tk.WORD, height=6,
                                                     font=("Consolas", 10), 
                                                     bg=ColorScheme.BG_LIGHT, fg=ColorScheme.TEXT_PRIMARY,
                                                     relief=tk.FLAT, borderwidth=2)
        self.notes_text.grid(row=0, column=0, sticky="nsew", padx=2, pady=(2, 8))
        
        # Notizen-Speichern Button
        save_notes_btn = ttk.Button(notes_frame, text="💾 Notizen speichern", 
                                     command=self.saveCurrentNotes,
                                     style="Secondary.TButton")
        save_notes_btn.grid(row=1, column=0, sticky="w", padx=2)

        # Button-Zeile
        button_frame = ttk.Frame(right_frame)
        button_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        button_frame.columnconfigure(4, weight=1)

        self.button_generate_key = ttk.Button(button_frame, text="🔐 SSH-Schlüssel", 
                                               command=self.generateKeyDialog,
                                               style="Primary.TButton")
        self.button_generate_key.grid(row=0, column=0, sticky="w")

        self.button_copy_pub = ttk.Button(button_frame, text="📋 Kopieren", 
                                           command=self.copyExistingPubKey,
                                           style="Secondary.TButton")
        self.button_copy_pub.grid(row=0, column=1, sticky="w", padx=(8, 0))

        self.button_connect_ssh = ttk.Button(button_frame, text="🚀 SSH", 
                                              command=self.connectNativeSsh,
                                              style="Success.TButton")
        self.button_connect_ssh.grid(row=0, column=2, sticky="w", padx=(8, 0))

        self.button_connect_putty = ttk.Button(button_frame, text="💻 PuTTY", 
                                                command=self.connectPutty,
                                                style="Success.TButton")
        self.button_connect_putty.grid(row=0, column=3, sticky="w", padx=(8, 0))

        if not self.putty_path:
            self.button_connect_putty.state(["disabled"])

        # Statusleiste
        self.status_var = tk.StringVar(value=self.getStatusText())
        status = ttk.Label(self, textvariable=self.status_var, anchor="w", padding=(Padding.FRAME, 4), 
                          relief=tk.SUNKEN, background=ColorScheme.STATUS_BG, foreground=ColorScheme.STATUS_TEXT)
        status.pack(fill=tk.X, side=tk.BOTTOM)

    def applyStyles(self) -> None:
        """Wendet modernes Design mit Farben und Schriftarten an"""
        style = ttk.Style()

        ui_font_family = getFirstAvailableFontFamily(["Segoe UI", "Noto Sans", "DejaVu Sans", "Liberation Sans", "Arial"])
        ui_font = (ui_font_family, 10) if ui_font_family else ("TkDefaultFont", 10)
        ui_font_bold = (ui_font_family, 10, "bold") if ui_font_family else ("TkDefaultFont", 10, "bold")
        ui_font_small = (ui_font_family, 9) if ui_font_family else ("TkDefaultFont", 9)
        ui_font_small_bold = (ui_font_family, 9, "bold") if ui_font_family else ("TkDefaultFont", 9, "bold")

        # Treeview Style
        style.configure("Custom.Treeview",
                       background=ColorScheme.LIST_ODD,
                       foreground=ColorScheme.TEXT_PRIMARY,
                       rowheight=28,
                       fieldbackground=ColorScheme.LIST_ODD,
                       font=ui_font)
        
        style.configure("Custom.Treeview.Heading",
                       background=ColorScheme.PRIMARY,
                       foreground=ColorScheme.TEXT_WHITE,
                       font=ui_font_bold)
        
        style.map("Custom.Treeview",
                 background=[('selected', ColorScheme.LIST_SELECTED)],
                 foreground=[('selected', ColorScheme.TEXT_PRIMARY)])
        
        # Alternierende Zeilen-Farben
        self.tree.tag_configure('oddrow', background=ColorScheme.LIST_ODD)
        self.tree.tag_configure('evenrow', background=ColorScheme.LIST_EVEN)
        
        # Button Styles
        style.configure("Primary.TButton", font=ui_font_small_bold, padding=Padding.BUTTON)
        style.configure("Secondary.TButton", font=ui_font_small, padding=Padding.BUTTON)
        style.configure("Success.TButton", font=ui_font_small_bold, padding=Padding.BUTTON)
        style.configure("Action.TButton", font=ui_font_small, padding=4)
        
        # Entry Style
        style.configure("Readonly.TEntry", fieldbackground=ColorScheme.BG_LIGHT, 
                       foreground=ColorScheme.TEXT_SECONDARY)
        
        # LabelFrame Style
        style.configure("TLabelframe", borderwidth=2, relief='solid')
        style.configure("TLabelframe.Label", font=ui_font_bold, 
                       foreground=ColorScheme.PRIMARY)
        
        self.configure(bg=ColorScheme.BG_LIGHT)

    def getStatusText(self) -> str:
        putty_state = "gefunden" if self.putty_path else "NICHT gefunden"
        return f"PuTTY: {putty_state} | Einträge: {len(self.entries)} | Doppelklick zum Verbinden"

    def setStatus(self, text: str) -> None:
        self.status_var.set(text)
        self.after(5000, lambda: self.status_var.set(self.getStatusText()))

    def loadEntries(self) -> None:
        parser = SshConfigParser()
        self.entries = parser.parseFile(self.config_path)
        self.filterEntries()
        self.setStatus(self.getStatusText())

    def filterEntries(self) -> None:
        """Filtert Einträge basierend auf Suchbegriff"""
        search_term = self.search_var.get().lower()

        for item in self.tree.get_children():
            self.tree.delete(item)

        row_count = 0
        for index, entry in enumerate(self.entries):
            if search_term:
                searchable = f"{entry.host_alias} {entry.options.get('hostname', '')} {entry.options.get('user', '')}".lower()
                if search_term not in searchable:
                    continue

            tag = 'evenrow' if row_count % 2 == 0 else 'oddrow'
            self.tree.insert("", "end", iid=str(index), values=(entry.getDisplayLine(),), tags=(tag,))
            row_count += 1

        self.clearDetails()

    def getHostHash(self, entry: SshHostEntry) -> str:
        """Erstellt einen Hash für den Host basierend auf hostname oder alias"""
        identifier = entry.options.get("hostname", entry.host_alias)
        return hashlib.md5(identifier.encode()).hexdigest()[:12]
    
    def getNotesPath(self, entry: SshHostEntry) -> Path:
        """Gibt den Pfad zur Notizen-Datei für einen Host zurück"""
        host_hash = self.getHostHash(entry)
        return self.notes_dir_path / f"{host_hash}.json"
    
    def loadNotes(self, entry: SshHostEntry) -> str:
        """Lädt gespeicherte Notizen für einen Host"""
        notes_file = self.getNotesPath(entry)
        if not notes_file.exists():
            return ""
        
        try:
            data = json.loads(notes_file.read_text(encoding="utf-8"))
            return data.get("notes", "")
        except Exception as e:
            print(f"Fehler beim Laden der Notizen: {e}")
            return ""
    
    def saveNotes(self, entry: SshHostEntry, notes: str) -> None:
        """Speichert Notizen für einen Host"""
        notes_file = self.getNotesPath(entry)
        
        try:
            data = {
                "host_alias": entry.host_alias,
                "hostname": entry.options.get("hostname", ""),
                "notes": notes,
                "hash": self.getHostHash(entry)
            }
            notes_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Speichern der Notizen:\n{e}")
    
    def saveCurrentNotes(self) -> None:
        """Speichert die aktuell angezeigten Notizen"""
        if self.selected_entry is None:
            messagebox.showinfo("Kein Host ausgewählt", "Bitte wählen Sie zuerst einen Host aus.")
            return
        
        notes = self.notes_text.get("1.0", tk.END).strip()
        self.saveNotes(self.selected_entry, notes)
        self.setStatus(f"✓ Notizen für '{self.selected_entry.host_alias}' gespeichert")

    def clearDetails(self) -> None:
        for key in self.detail_vars:
            self.detail_vars[key].set("")
        self.notes_text.delete("1.0", tk.END)
        self.selected_entry = None

    def onSelectEntry(self, _event: object) -> None:
        selection = self.tree.selection()
        if not selection:
            return

        index = int(selection[0])
        self.selected_entry = self.entries[index]
        self.showDetails(self.selected_entry)

    def showDetails(self, entry: SshHostEntry) -> None:
        self.detail_vars["host_alias"].set(entry.host_alias)
        self.detail_vars["hostname"].set(entry.options.get("hostname", ""))
        self.detail_vars["user"].set(entry.options.get("user", ""))
        self.detail_vars["port"].set(entry.options.get("port", ""))
        self.detail_vars["identityfile"].set(entry.options.get("identityfile", ""))

        # Notizen laden
        self.notes_text.delete("1.0", tk.END)
        saved_notes = self.loadNotes(entry)
        if saved_notes:
            self.notes_text.insert("1.0", saved_notes)

    def openSshFolder(self) -> None:
        self.ssh_dir_path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(self.ssh_dir_path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.ssh_dir_path)])
            else:
                subprocess.Popen(["xdg-open", str(self.ssh_dir_path)])
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Ordner nicht öffnen:\n{e}")

    def openSessionLogs(self) -> None:
        """Öffnet den Session-Logs-Ordner"""
        self.session_logs_dir_path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(self.session_logs_dir_path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.session_logs_dir_path)])
            else:
                subprocess.Popen(["xdg-open", str(self.session_logs_dir_path)])
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Ordner nicht öffnen:\n{e}")

    def copyToClipboard(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    def resolveIdentityPath(self, identity_value: str) -> Path:
        expanded = os.path.expandvars(identity_value)
        expanded = os.path.expanduser(expanded)
        return Path(expanded)

    def getKeyFilename(self, key_type: str, key_name: str) -> str:
        """Generiert Dateinamen für SSH-Schlüssel"""
        if key_name:
            return f"id_{key_type}_{key_name}"
        else:
            return f"id_{key_type}"

    def generateKeyDialog(self) -> None:
        """Öffnet Dialog für SSH-Schlüsselgenerierung"""
        dialog = KeyGenerationDialog(self)
        self.wait_window(dialog)
        
        if dialog.result is None:
            return
        
        key_type = dialog.result['key_type']
        key_name = dialog.result['key_name']
        update_config = dialog.result['update_config']
        
        self.generateKey(key_type, key_name, update_config)

    def generateKey(self, key_type: str, key_name: str, update_config: bool) -> None:
        """Generiert SSH-Schlüssel mit gewählten Parametern"""
        self.ssh_dir_path.mkdir(parents=True, exist_ok=True)
        
        filename = self.getKeyFilename(key_type, key_name)
        private_key_path = self.ssh_dir_path / filename
        public_key_path = self.ssh_dir_path / f"{filename}.pub"
        
        if private_key_path.exists() or public_key_path.exists():
            result = messagebox.askyesno(
                "Schlüssel existiert",
                f"Schlüssel existiert bereits:\n{private_key_path}\n\nÜberschreiben?",
            )
            if not result:
                return
        
        # Befehl erstellen
        if key_type == "rsa":
            command = ["ssh-keygen", "-t", "rsa", "-b", "4096", "-f", str(private_key_path), "-N", ""]
        elif key_type == "ecdsa":
            command = ["ssh-keygen", "-t", "ecdsa", "-b", "521", "-f", str(private_key_path), "-N", ""]
        else:  # ed25519
            command = ["ssh-keygen", "-t", "ed25519", "-f", str(private_key_path), "-N", ""]
        
        try:
            subprocess.check_call(command)
        except FileNotFoundError:
            messagebox.showerror(
                "ssh-keygen nicht gefunden",
                "ssh-keygen wurde nicht in PATH gefunden. Installieren Sie den Windows OpenSSH Client.",
            )
            return
        except subprocess.CalledProcessError as exc:
            messagebox.showerror("Fehler", f"ssh-keygen ist fehlgeschlagen: {exc}")
            return
        
        # Public Key kopieren
        self.copyPubKeyIfExists(public_key_path)
        
        # Zu Config hinzufügen wenn gewünscht
        if update_config and self.selected_entry:
            self.addKeyToConfig(self.selected_entry, private_key_path)
        
        # In Notizen anzeigen
        self.showKeyInNotes(private_key_path, public_key_path)
        
        messagebox.showinfo("Erfolg", 
                          f"SSH-Schlüssel erfolgreich generiert!\n\n"
                          f"Typ: {key_type}\n"
                          f"Datei: {filename}\n"
                          f"Öffentlicher Schlüssel wurde kopiert.")

    def addKeyToConfig(self, entry: SshHostEntry, key_path: Path) -> None:
        """Fügt IdentityFile zur SSH-Config hinzu"""
        try:
            config_content = self.config_path.read_text(encoding="utf-8")
            
            # Suche Host-Block
            lines = config_content.split('\n')
            new_lines = []
            in_target_host = False
            identity_added = False
            
            for line in lines:
                new_lines.append(line)
                
                if line.strip().lower().startswith('host ') and entry.host_alias in line:
                    in_target_host = True
                elif in_target_host and line.strip().lower().startswith('host '):
                    in_target_host = False
                elif in_target_host and not identity_added and line.strip() and not line.strip().startswith('#'):
                    # Füge IdentityFile nach erster Zeile im Host-Block ein
                    new_lines.append(f"  IdentityFile {key_path}")
                    identity_added = True
            
            if identity_added:
                self.config_path.write_text('\n'.join(new_lines), encoding="utf-8")
                self.setStatus(f"✓ IdentityFile zu '{entry.host_alias}' hinzugefügt")
                self.loadEntries()
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Aktualisieren der Config:\n{e}")

    def showKeyInNotes(self, private_key_path: Path, public_key_path: Path) -> None:
        """Zeigt Schlüssel-Informationen in den Notizen an"""
        if self.selected_entry is None:
            return
        
        current_notes = self.notes_text.get("1.0", tk.END).strip()
        
        key_info = f"\n\n━━━ SSH-Schlüssel ━━━\n"
        key_info += f"Privat: {private_key_path}\n"
        key_info += f"Öffentlich: {public_key_path}\n"
        key_info += f"\nHinweis: Öffentlicher Schlüssel wurde in die Zwischenablage kopiert.\n"
        
        if current_notes:
            self.notes_text.insert(tk.END, key_info)
        else:
            self.notes_text.insert("1.0", key_info.strip())

    def copyExistingPubKey(self) -> None:
        """Kopiert existierenden Public Key"""
        # Versuche Standard-Schlüssel
        possible_keys = [
            self.ssh_dir_path / "id_ed25519.pub",
            self.ssh_dir_path / "id_rsa.pub",
            self.ssh_dir_path / "id_ecdsa.pub",
        ]
        
        # Wenn Host ausgewählt, prüfe auch dessen IdentityFile
        if self.selected_entry:
            identity = self.selected_entry.options.get("identityfile", "")
            if identity:
                identity_path = self.resolveIdentityPath(identity)
                possible_keys.insert(0, identity_path.with_suffix('.pub'))
        
        for pub_key_path in possible_keys:
            if pub_key_path.exists():
                self.copyPubKeyIfExists(pub_key_path)
                return
        
        messagebox.showerror("Kein Schlüssel gefunden", 
                           "Kein öffentlicher SSH-Schlüssel gefunden.\n\n"
                           "Generieren Sie zuerst einen Schlüssel.")

    def copyPubKeyIfExists(self, public_key_path: Path) -> None:
        if not public_key_path.exists():
            messagebox.showerror("Fehler", f"Öffentlicher Schlüssel nicht gefunden:\n{public_key_path}")
            return

        pub_text = public_key_path.read_text(encoding="utf-8", errors="ignore").strip()
        if not pub_text:
            messagebox.showerror("Fehler", f"Öffentlicher Schlüssel ist leer:\n{public_key_path}")
            return

        self.copyToClipboard(pub_text)
        self.setStatus(f"✓ {public_key_path.name} in Zwischenablage kopiert")

    def findPuttyPath(self) -> Optional[str]:
        if self.isExecutableInPath("putty.exe") or self.isExecutableInPath("putty"):
            return "putty"

        candidates = [
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "PuTTY" / "putty.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "PuTTY" / "putty.exe",
            Path.home() / "Downloads" / "putty.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    def isExecutableInPath(self, name: str) -> bool:
        paths = os.environ.get("PATH", "").split(os.pathsep)
        for path in paths:
            candidate = Path(path) / name
            if candidate.exists():
                return True
        return False

    def logSession(self, host_alias: str, connection_type: str, success: bool = True) -> None:
        """Protokolliert eine SSH-Sitzung in einer Datei"""
        try:
            # Erstelle eine Logdatei pro Host
            log_file = self.session_logs_dir_path / f"{host_alias}.log"
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            host_name = self.selected_entry.options.get("hostname", "N/A") if self.selected_entry else "N/A"
            user_name = self.selected_entry.options.get("user", "N/A") if self.selected_entry else "N/A"
            port = self.selected_entry.options.get("port", "22") if self.selected_entry else "22"
            
            status = "✓ Erfolg" if success else "✗ Fehler"
            
            log_entry = f"[{timestamp}] {connection_type} ({status}) | user@host: {user_name}@{host_name}:{port}\n"
            
            # Anhängen an Logdatei
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Fehler beim Schreiben des Session-Logs: {e}")

    def connectNativeSsh(self) -> None:
        if self.selected_entry is None:
            messagebox.showinfo("Kein Host ausgewählt", "Bitte wählen Sie zuerst einen Host aus.")
            return

        host_alias = self.selected_entry.host_alias

        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["start", "cmd", "/k", "ssh", host_alias], shell=True)
            elif sys.platform == "darwin":
                script = f'tell application "Terminal" to do script "ssh {host_alias}"'
                subprocess.Popen(["osascript", "-e", script])
            else:
                command_args = ["ssh", host_alias]

                terminal_candidates: list[tuple[str, list[str]]] = [
                    ("gnome-terminal", ["gnome-terminal", "--"]),
                    ("konsole", ["konsole", "-e"]),
                    ("xterm", ["xterm", "-e"]),
                    ("x-terminal-emulator", ["x-terminal-emulator", "-e"]),
                    ("kitty", ["kitty", "-e"]),
                    ("alacritty", ["alacritty", "-e"]),
                    ("wezterm", ["wezterm", "start", "--"]),
                ]

                for terminal_name, terminal_prefix in terminal_candidates:
                    if self.isExecutableInPath(terminal_name):
                        subprocess.Popen(terminal_prefix + command_args)
                        break
                else:
                    messagebox.showerror(
                        "Kein Terminal gefunden",
                        "Kein unterstütztes Terminal gefunden. Installieren Sie z.B. gnome-terminal, konsole oder xterm.",
                    )
                    return

            self.logSession(host_alias, "SSH")
            self.setStatus(f"✓ SSH-Verbindung gestartet: {host_alias}")
        except Exception as exc:
            self.logSession(host_alias, "SSH", success=False)
            messagebox.showerror("Fehler", f"SSH-Verbindung fehlgeschlagen:\n{exc}")

    def connectPutty(self) -> None:
        if self.selected_entry is None:
            messagebox.showinfo("Kein Host ausgewählt", "Bitte wählen Sie zuerst einen Host aus.")
            return

        if not self.putty_path:
            messagebox.showerror("PuTTY nicht gefunden", 
                               "PuTTY wurde nicht gefunden. Installieren Sie PuTTY oder fügen Sie putty.exe zu PATH hinzu.")
            return

        host_name = self.selected_entry.options.get("hostname", self.selected_entry.host_alias)
        user_name = self.selected_entry.options.get("user", "")
        port = self.selected_entry.options.get("port", "")

        target = f"{user_name}@{host_name}" if user_name else host_name

        command = [self.putty_path, "-ssh", target]
        if port:
            command += ["-P", port]

        try:
            subprocess.Popen(command)
            self.logSession(self.selected_entry.host_alias, "PuTTY")
            self.setStatus(f"✓ PuTTY gestartet: {target}")
        except Exception as exc:
            self.logSession(self.selected_entry.host_alias, "PuTTY", success=False)
            messagebox.showerror("Fehler", f"PuTTY fehlgeschlagen:\n{exc}")


if __name__ == "__main__":
    app = SshGui()
    app.mainloop()
