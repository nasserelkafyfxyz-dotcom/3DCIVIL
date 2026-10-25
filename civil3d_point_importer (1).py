#!/usr/bin/env python3
"""
BY NASSER ELKA 
for any question or suggestion, please contact me 0699899302 nasser
"""
import argparse
import os
import re
import statistics
import sys

SPLIT = {
    "tab": lambda l: l.split("\t"),
    "semicolon": lambda l: l.split(";"),
    "comma": lambda l: re.split(r"\s*,\s*", l),
    "space": lambda l: re.split(r"\s+", l),
}
OUT_SEP = {"comma": ",", "space": " ", "tab": "\t", "semicolon": ";"}
NUM_RE = re.compile(r"^[+-]?(\d+([.,]\d*)?|[.,]\d+)$")


def num(s):
    s = str(s).strip()
    if not NUM_RE.match(s):
        return None
    return float(s.replace(",", "."))


def consistency(sample, fn):
    counts = {}
    for l in sample:
        n = len(fn(l))
        counts[n] = counts.get(n, 0) + 1
    n, c = max(counts.items(), key=lambda kv: kv[1])
    return n, c / len(sample)


def detect_separator(sample):
    for d in ("tab", "semicolon"):
        n, r = consistency(sample, SPLIT[d])
        if n >= 3 and r >= 0.7:
            return d
    cn, cr = consistency(sample, SPLIT["comma"])
    sn, sr = consistency(sample, SPLIT["space"])
    space_ok = sn >= 3 and sr >= 0.7
    comma_spaced = sum(1 for l in sample if re.search(r",\s|\s,", l)) > len(sample) * 0.5
    if cn >= 3 and cr >= 0.7 and (not space_ok or comma_spaced):
        return "comma"
    if space_ok:
        return "space"
    return "comma" if cn > sn else "space"


def parse_text(text, in_sep="auto"):
    lines = [l.strip() for l in text.replace("\r", "").split("\n")]
    lines = [l for l in lines if l and not re.match(r"^(#|//|;)", l)]
    if not lines:
        return [], None, "space"
    sep = detect_separator(lines[:60]) if in_sep == "auto" else in_sep
    rows, header = [], None
    for l in lines:
        r = [x.strip().strip('"') for x in SPLIT[sep](l)]
        n_num = sum(1 for x in r if num(x) is not None)
        if len(r) >= 3 and n_num >= 2:
            rows.append(r)
        elif header is None and not rows and len(r) >= 3:
            header = [x.lower() for x in r]
    return rows, header, sep


def read_text(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def guess_roles(rows, header):
    sample = rows[:200]
    n = max(len(r) for r in sample)
    stats = []
    for j in range(n):
        v = [r[j] for r in sample if j < len(r) and r[j] != ""]
        k = len(v) or 1
        nums = [num(x) for x in v]
        nn = [abs(x) for x in nums if x is not None]
        stats.append({
            "numF": len(nn) / k,
            "intF": sum(1 for x in v if re.fullmatch(r"\d+", x)) / k,
            "uniq": len(set(v)) / k,
            "mag": statistics.median(nn) if nn and len(nn) / k > 0.5 else 0,
        })
    roles = ["-"] * n
    if header:
        pats = {
            "ID": r"^(id|pt|pts|point|points|pnt|no|num|numero|name|nom|n°)$",
            "X": r"^(x|e|east|easting|est|abscisse)$",
            "Y": r"^(y|north|northing|nord|ordonnee|ordonnée)$",
            "Z": r"^(z|h|alt|altitude|elev|elevation|cote)$",
            "DESC": r"desc|code|nature|obs",
        }
        for j, h in enumerate(header[:n]):
            for k, p in pats.items():
                if re.search(p, h):
                    roles[j] = k
                    break
        if "X" in roles and "Y" in roles:
            return roles
        roles = ["-"] * n
    s = 0
    c0 = stats[0]
    if n >= 3 and (c0["numF"] < 0.5 or (c0["intF"] > 0.9 and c0["uniq"] > 0.95
                                         and stats[1]["mag"] > 5 * c0["mag"])):
        roles[0] = "ID"
        s = 1
    for i, k in enumerate(("X", "Y", "Z")):
        j = s + i
        if j < n and stats[j]["numF"] > 0.9:
            roles[j] = k
    for j in range(s + 3, n):
        roles[j] = "DESC"
    return roles


def build_points(rows, roles):
    ix, iy = roles.index("X"), roles.index("Y")
    iz = roles.index("Z") if "Z" in roles else -1
    ii = roles.index("ID") if "ID" in roles else -1
    dd = [j for j, r in enumerate(roles) if r == "DESC"]
    pts, skipped = [], 0
    get = lambda r, j: r[j] if j < len(r) else ""
    for r in rows:
        x, y = num(get(r, ix)), num(get(r, iy))
        if x is None or y is None:
            skipped += 1
            continue
        z = num(get(r, iz)) if iz >= 0 else None
        pid = get(r, ii) if ii >= 0 and get(r, ii) else str(len(pts) + 1)
        desc = " ".join(get(r, j) for j in dd if get(r, j)).strip()
        pts.append({"id": pid, "x": x, "y": y, "z": z, "d": desc})
    return pts, skipped


def render(pts, fmt, sep, dec):
    t = lambda v: f"{(0.0 if v is None else v):.{dec}f}"
    clean = (lambda s: re.sub(r"\s+", "_", s)) if sep == " " else \
            (lambda s: re.sub(r"\s+", " ", s.replace(sep, " ")))
    out = []
    for p in pts:
        if fmt == "SCR":
            out.append(f"POINT {t(p['x'])},{t(p['y'])},{t(p['z'])}")
            continue
        fields = [clean(p["id"])]
        fields += [t(p["y"]), t(p["x"])] if fmt == "PNEZ" else [t(p["x"]), t(p["y"])]
        fields.append(t(p["z"]))
        if p["d"]:
            fields.append(clean(p["d"]))
        out.append(sep.join(fields))
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------------------
# Window (same layout as the web tool: 1. points  2. columns  3. export)
# ----------------------------------------------------------------------------
EXAMPLE = ("P1 452310.25 3521877.10 112.40 CORNER\n"
           "P2 452318.90 3521880.55 112.85 CORNER\n"
           "P3 452330.12 3521892.31 113.10 TREE\n"
           "P4 452341.77 3521901.04 113.62 POLE\n"
           "P5 452350.00 3521915.66 114.05 CORNER")
LBL = {"ID": "Point number", "X": "X / Easting", "Y": "Y / Northing",
       "Z": "Z / Elevation", "DESC": "Description", "-": "Ignore"}
LBL_REV = {v: k for k, v in LBL.items()}
SEP_LBL = {"Auto-detect": "auto", "Space": "space", "Tab": "tab", "Comma": "comma", "Semicolon": "semicolon"}
OUT_LBL = {"Comma": "comma", "Space": "space", "Tab": "tab", "Semicolon": "semicolon"}
FMT_LBL = {"PNEZ - point, northing, easting, elevation": "PNEZ",
           "PENZ - point, easting, northing, elevation": "PENZ",
           "Script - POINT commands": "SCR"}
ACC, INK, MUTE, BG, SURF, WARN = "#0b6e6e", "#14232e", "#5d6f7b", "#eef2f4", "#ffffff", "#a85a00"


def run_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    root = tk.Tk()
    root.title("Civil 3D Point Importer")
    root.geometry("980x860")
    root.configure(bg=BG)
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    st.configure("TFrame", background=BG)
    st.configure("Box.TLabelframe", background=SURF, bordercolor="#cfd9de")
    st.configure("Box.TLabelframe.Label", background=SURF, foreground=INK, font=("Segoe UI", 11, "bold"))
    st.configure("TLabel", background=SURF, foreground=INK, font=("Segoe UI", 10))
    st.configure("Mute.TLabel", foreground=MUTE)
    st.configure("Warn.TLabel", foreground=WARN)
    st.configure("TButton", font=("Segoe UI", 10), padding=6)
    st.configure("Accent.TButton", background=ACC, foreground="white", font=("Segoe UI", 10, "bold"))
    st.map("Accent.TButton", background=[("active", "#095858")])

    state = {"rows": [], "header": None, "roles": [], "pts": [], "skipped": 0}

    # scrollable page
    outer = ttk.Frame(root)
    outer.pack(fill="both", expand=True)
    cv = tk.Canvas(outer, bg=BG, highlightthickness=0)
    sb = ttk.Scrollbar(outer, orient="vertical", command=cv.yview)
    page = ttk.Frame(cv)
    page.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
    win = cv.create_window((0, 0), window=page, anchor="nw")
    cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
    cv.configure(yscrollcommand=sb.set)
    cv.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    cv.bind_all("<MouseWheel>", lambda e: cv.yview_scroll(int(-e.delta / 120) if e.delta else 0, "units"))

    ttk.Label(page, text="Civil 3D point importer", background=BG, foreground=INK,
              font=("Georgia", 20, "bold")).pack(anchor="w", padx=16, pady=(14, 0))
    ttk.Label(page, background=BG, foreground=MUTE, wraplength=800, justify="left",
              text="Open your point file as it is. The tool finds the separator, the point number and the "
                   "X, Y, Z columns, then gives you a file Civil 3D reads without any format setup."
              ).pack(anchor="w", padx=16, pady=(0, 12))

    # 1. points
    b1 = ttk.LabelFrame(page, text="1. Your points", style="Box.TLabelframe", padding=10)
    b1.pack(fill="x", padx=16, pady=6)
    src = tk.Text(b1, height=7, font=("Consolas", 10), bg=BG, fg=INK, relief="solid", bd=1, wrap="none")
    src.pack(fill="x")
    r1 = tk.Frame(b1, bg=SURF)
    r1.pack(fill="x", pady=(8, 0))
    in_var = tk.StringVar(value="Auto-detect")
    det_var = tk.StringVar()

    def set_text(t):
        src.delete("1.0", "end")
        src.insert("1.0", t)
        reload()

    def open_files():
        fs = filedialog.askopenfilenames(
            title="Choose point file(s)",
            filetypes=[("Point files", "*.txt *.csv *.xyz *.pts *.asc *.dat *.prn"), ("All files", "*.*")])
        if fs:
            set_text("\n".join(read_text(f).strip() for f in fs))

    ttk.Button(r1, text="Open file(s)", command=open_files).pack(side="left")
    ttk.Button(r1, text="Load an example", command=lambda: set_text(EXAMPLE)).pack(side="left", padx=6)
    ttk.Button(r1, text="Clear", command=lambda: set_text("")).pack(side="left")
    ttk.Label(r1, text="Separator").pack(side="left", padx=(16, 4))
    cb_in = ttk.Combobox(r1, textvariable=in_var, values=list(SEP_LBL), state="readonly", width=12)
    cb_in.pack(side="left")
    ttk.Label(r1, textvariable=det_var, style="Mute.TLabel").pack(side="left", padx=10)

    # 2. columns
    b2 = ttk.LabelFrame(page, text="2. Check the columns", style="Box.TLabelframe", padding=10)
    ttk.Label(b2, style="Mute.TLabel",
              text="Columns were assigned automatically. Change a column's role if one is wrong."
              ).pack(anchor="w", pady=(0, 6))
    grid = tk.Frame(b2, bg=SURF)
    grid.pack(fill="x")
    r2 = tk.Frame(b2, bg=SURF)
    r2.pack(fill="x", pady=(8, 0))
    msg_var = tk.StringVar()
    ttk.Button(r2, text="Swap X and Y", command=lambda: swap()).pack(side="left")
    ttk.Label(r2, textvariable=msg_var, style="Warn.TLabel").pack(side="left", padx=10)

    # 3. export
    b3 = ttk.LabelFrame(page, text="3. Export for Civil 3D", style="Box.TLabelframe", padding=10)
    stats = tk.Frame(b3, bg=SURF)
    stats.pack(fill="x")
    warn_var = tk.StringVar()
    ttk.Label(b3, textvariable=warn_var, style="Warn.TLabel", wraplength=860, justify="left").pack(anchor="w", pady=4)
    r3 = tk.Frame(b3, bg=SURF)
    r3.pack(fill="x", pady=4)
    fmt_var = tk.StringVar(value=list(FMT_LBL)[0])
    sep_var = tk.StringVar(value="Comma")
    dec_var = tk.StringVar(value="3")
    ttk.Label(r3, text="Format").pack(side="left")
    cb_f = ttk.Combobox(r3, textvariable=fmt_var, values=list(FMT_LBL), state="readonly", width=40)
    cb_f.pack(side="left", padx=(4, 12))
    ttk.Label(r3, text="Output separator").pack(side="left")
    cb_s = ttk.Combobox(r3, textvariable=sep_var, values=list(OUT_LBL), state="readonly", width=10)
    cb_s.pack(side="left", padx=(4, 12))
    ttk.Label(r3, text="Decimals").pack(side="left")
    cb_d = ttk.Combobox(r3, textvariable=dec_var, values=["2", "3", "4"], state="readonly", width=4)
    cb_d.pack(side="left", padx=4)
    r3b = tk.Frame(b3, bg=SURF)
    r3b.pack(fill="x", pady=4)
    pv = tk.Text(b3, height=12, font=("Consolas", 10), bg=BG, fg=INK, relief="solid", bd=1, wrap="none",
                 state="disabled")
    pv.pack(fill="x", pady=(6, 0))
    how_var = tk.StringVar()
    ttk.Label(b3, textvariable=how_var, style="Mute.TLabel", wraplength=860, justify="left").pack(anchor="w", pady=(8, 0))

    def current_output():
        return render(state["pts"], FMT_LBL[fmt_var.get()], OUT_SEP[OUT_LBL[sep_var.get()]], int(dec_var.get()))

    def save():
        if not state["pts"]:
            return
        f = FMT_LBL[fmt_var.get()]
        sp = OUT_SEP[OUT_LBL[sep_var.get()]]
        ext = ".scr" if f == "SCR" else (".csv" if sp == "," else ".txt")
        p = filedialog.asksaveasfilename(title="Save file", defaultextension=ext,
                                         initialfile="points_" + f + ext)
        if p:
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(current_output())
            messagebox.showinfo("Saved", f"{len(state['pts'])} points saved to\n{p}")

    def copy():
        root.clipboard_clear()
        root.clipboard_append(current_output())
        btn_copy.config(text="Copied")
        root.after(1500, lambda: btn_copy.config(text="Copy"))

    ttk.Button(r3b, text="Save file", style="Accent.TButton", command=save).pack(side="left")
    btn_copy = ttk.Button(r3b, text="Copy", command=copy)
    btn_copy.pack(side="left", padx=6)

    def swap():
        r = state["roles"]
        if "X" in r and "Y" in r:
            a, b = r.index("X"), r.index("Y")
            r[a], r[b] = "Y", "X"
            draw()

    def on_role(j, var):
        v = LBL_REV[var.get()]
        r = state["roles"]
        if v not in ("DESC", "-"):
            for i in range(len(r)):
                if i != j and r[i] == v:
                    r[i] = "-"
        r[j] = v
        draw()

    def draw():
        for w in grid.winfo_children():
            w.destroy()
        rows, roles = state["rows"], state["roles"]
        show = min(len(roles), 10)
        for j in range(show):
            var = tk.StringVar(value=LBL[roles[j]])
            cb = ttk.Combobox(grid, textvariable=var, values=list(LBL.values()), state="readonly", width=14)
            cb.grid(row=0, column=j, padx=2, pady=2, sticky="ew")
            cb.bind("<<ComboboxSelected>>", lambda e, j=j, v=var: on_role(j, v))
            grid.columnconfigure(j, weight=1)
        for i, r in enumerate(rows[:8]):
            for j in range(show):
                tk.Label(grid, text=r[j] if j < len(r) else "", font=("Consolas", 10), bg=SURF, fg=INK,
                         relief="solid", bd=1, anchor="w", padx=4).grid(row=i + 1, column=j, sticky="ew")
        update()

    def update():
        roles = state["roles"]
        for w in stats.winfo_children():
            w.destroy()
        warn_var.set("")
        pv.config(state="normal")
        pv.delete("1.0", "end")
        state["pts"] = []
        if "X" not in roles or "Y" not in roles:
            msg_var.set("Set one column as X and one as Y.")
            pv.config(state="disabled")
            return
        msg_var.set("")
        pts, skipped = build_points(state["rows"], roles)
        state["pts"] = pts

        def rg(k):
            v = [p[k] for p in pts if p[k] is not None]
            return f"{min(v):.2f} to {max(v):.2f}" if v else "none"

        for i, (a, b) in enumerate([("Points", str(len(pts))), ("X range", rg("x")),
                                    ("Y range", rg("y")), ("Z range", rg("z"))]):
            f = tk.Frame(stats, bg=SURF, highlightbackground=ACC, highlightthickness=0)
            f.grid(row=0, column=i, padx=(0, 18), sticky="w")
            tk.Frame(f, bg=ACC, width=3).pack(side="left", fill="y")
            inner = tk.Frame(f, bg=SURF)
            inner.pack(side="left", padx=8)
            tk.Label(inner, text=a, bg=SURF, fg=MUTE, font=("Segoe UI", 9)).pack(anchor="w")
            tk.Label(inner, text=b, bg=SURF, fg=INK, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        w = []
        ids = [p["id"] for p in pts]
        if len(ids) != len(set(ids)):
            w.append(f"{len(ids) - len(set(ids))} duplicate point number(s). Civil 3D will ask what to do with them on import.")
        nz = sum(1 for p in pts if p["z"] is None)
        if nz:
            w.append(f"{nz} point(s) have no elevation. They are exported with Z = 0.")
        if skipped:
            w.append(f"{skipped} line(s) skipped because X or Y is not a number.")
        warn_var.set("")
        pv.config(state="normal")
        pv.delete("1.0", "end")
        state["pts"] = []
        if "X" not in roles or "Y" not in roles:
            msg_var.set("Set one column as X and one as Y.")
            pv.config(state="disabled")
            return
        msg_var.set("")
        pts, skipped = build_points(state["rows"], roles)
        state["pts"] = pts

        def rg(k):
            v = [p[k] for p in pts if p[k] is not None]
            return f"{min(v):.2f} to {max(v):.2f}" if v else "none"

        for i, (a, b) in enumerate([("Points", str(len(pts))), ("X range", rg("x")),
                                    ("Y range", rg("y")), ("Z range", rg("z"))]):
            f = tk.Frame(stats, bg=SURF, highlightbackground=ACC, highlightthickness=0)
            f.grid(row=0, column=i, padx=(0, 18), sticky="w")
            tk.Frame(f, bg=ACC, width=3).pack(side="left", fill="y")
            inner = tk.Frame(f, bg=SURF)
            inner.pack(side="left", padx=8)
            tk.Label(inner, text=a, bg=SURF, fg=MUTE, font=("Segoe UI", 9)).pack(anchor="w")
            tk.Label(inner, text=b, bg=SURF, fg=INK, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        w = []
        ids = [p["id"] for p in pts]
        if len(ids) != len(set(ids)):
            w.append(f"{len(ids) - len(set(ids))} duplicate point number(s). Civil 3D will ask what to do with them on import.")
        nz = sum(1 for p in pts if p["z"] is None)
        if nz:
            w.append(f"{nz} point(s) have no elevation. They are exported with Z = 0.")
        if skipped:
            w.append(f"{skipped} line(s) skipped because X or Y is not a number.")
        if len(pts) > 2 and abs(statistics.median(p["x"] for p in pts)) < 0.2 * abs(statistics.median(p["y"] for p in pts)):
            w.append('X looks much smaller than Y. If the file has northing first, use "Swap X and Y".')
        warn_var.set("\n".join(w))
        out = current_output().split("\n")
        pv.insert("1.0", "\n".join(out[:12]) + ("\n..." if len(pts) > 12 else ""))
        pv.config(state="disabled")
        f = FMT_LBL[fmt_var.get()]
        how_var.set("In Civil 3D, run the SCRIPT command and pick the .scr file. It draws the points as AutoCAD POINT objects."
                    if f == "SCR" else
                    f'In Civil 3D: Create Points > Import Points, choose "{f} ({sep_var.get().lower()} delimited)" '
                    "as the format, then add the file. If that exact format is not in the list, pick the closest "
                    'one or create it with "Add format".')

    def reload(*_):
        text = src.get("1.0", "end")
        rows, header, sep = parse_text(text, SEP_LBL[in_var.get()])
        state.update(rows=rows, header=header)
        if not rows:
            state["roles"] = []
            b2.pack_forget()
            b3.pack_forget()
            det_var.set("")
            return
        det_var.set("Detected separator: " + sep if SEP_LBL[in_var.get()] == "auto" else "")
        state["roles"] = guess_roles(rows, header)
        b2.pack(fill="x", padx=16, pady=6)
        b3.pack(fill="x", padx=16, pady=6)
        draw()

    src.bind("<KeyRelease>", reload)
    src.bind("<<Paste>>", lambda e: root.after(50, reload))
    cb_in.bind("<<ComboboxSelected>>", reload)
    for c in (cb_f, cb_s, cb_d):
        c.bind("<<ComboboxSelected>>", lambda e: update() if state["rows"] else None)
    root.mainloop()


def run_cli(a):
    path = a.file
    if not os.path.isfile(path):
        sys.exit("No valid file selected.")
    rows, header, sep = parse_text(read_text(path), a.in_sep)
    if not rows:
        sys.exit("No point lines found (need at least 3 columns with 2 numbers).")
    roles = [r.strip().upper() for r in a.cols.split(",")] if a.cols else guess_roles(rows, header)
    if "X" not in roles or "Y" not in roles:
        sys.exit(f"Could not find X and Y columns. Detected roles: {roles}. Use --cols to set them.")
    if a.swap:
        ix, iy = roles.index("X"), roles.index("Y")
        roles[ix], roles[iy] = "Y", "X"
    pts, skipped = build_points(rows, roles)
    ids = [p["id"] for p in pts]
    print(f"Input separator : {sep}\nColumn roles    : {roles}\nPoints          : {len(pts)}")
    if len(ids) != len(set(ids)):
        print(f"WARNING: {len(ids) - len(set(ids))} duplicate point number(s).")
    if skipped:
        print(f"WARNING: {skipped} line(s) skipped (X or Y not numeric).")
    sepc = OUT_SEP[a.out_sep]
    ext = ".scr" if a.format == "SCR" else (".csv" if sepc == "," else ".txt")
    out = a.output or os.path.splitext(path)[0] + f"_{a.format}{ext}"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(render(pts, a.format, sepc, a.decimals))
    print(f"Saved           : {out}")


def main():
    ap = argparse.ArgumentParser(description="Convert point files for Civil 3D import.")
    ap.add_argument("file", nargs="?")
    ap.add_argument("-f", "--format", default="PNEZ", choices=["PNEZ", "PENZ", "SCR"], type=str.upper)
    ap.add_argument("-s", "--out-sep", default="comma", choices=list(OUT_SEP))
    ap.add_argument("-i", "--in-sep", default="auto", choices=["auto"] + list(SPLIT))
    ap.add_argument("-d", "--decimals", type=int, default=3)
    ap.add_argument("-o", "--output")
    ap.add_argument("--swap", action="store_true")
    ap.add_argument("--cols")
    a = ap.parse_args()
    if a.file:
        run_cli(a)
    else:
        run_gui()


if __name__ == "__main__":
    main()
