# ACEestFull.py
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime, date
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from fpdf import FPDF
import random

DB_NAME = "aceest_fitness.db"

# ---------- DATABASE INITIALIZATION ----------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Users (for role-based login)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT,
        role TEXT
    )
    """)
    
    # Clients
    cur.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        age INTEGER,
        height REAL,
        weight REAL,
        program TEXT,
        calories INTEGER,
        target_weight REAL,
        target_adherence INTEGER,
        membership_status TEXT,
        membership_end TEXT
    )
    """)
    
    # Progress
    cur.execute("""
    CREATE TABLE IF NOT EXISTS progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_name TEXT,
        week TEXT,
        adherence INTEGER
    )
    """)
    
    # Workouts
    cur.execute("""
    CREATE TABLE IF NOT EXISTS workouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_name TEXT,
        date TEXT,
        workout_type TEXT,
        duration_min INTEGER,
        notes TEXT
    )
    """)
    
    # Exercises
    cur.execute("""
    CREATE TABLE IF NOT EXISTS exercises (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workout_id INTEGER,
        name TEXT,
        sets INTEGER,
        reps INTEGER,
        weight REAL
    )
    """)
    
    # Metrics
    cur.execute("""
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_name TEXT,
        date TEXT,
        weight REAL,
        waist REAL,
        bodyfat REAL
    )
    """)
    
    # Add default admin if not exists
    cur.execute("SELECT * FROM users WHERE username='admin'")
    if not cur.fetchone():
        cur.execute("INSERT INTO users VALUES ('admin','admin','Admin')")
    
    conn.commit()
    conn.close()

# ---------- MAIN APPLICATION ----------
class ACEestApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ACEest Fitness & Performance")
        self.root.geometry("1400x900")
        self.root.configure(bg="#1a1a1a")
        
        self.conn = sqlite3.connect(DB_NAME)
        self.cur = self.conn.cursor()
        
        self.current_user = None
        self.current_client = None
        
        # Programs for AI-style generation
        self.program_templates = {
            "Fat Loss": ["Full Body HIIT", "Circuit Training", "Cardio + Weights"],
            "Muscle Gain": ["Push/Pull/Legs", "Upper/Lower Split", "Full Body Strength"],
            "Beginner": ["Full Body 3x/week", "Light Strength + Mobility"]
        }
        
        self.login_screen()
    
    # ---------- LOGIN SCREEN ----------
    def login_screen(self):
        self.clear_root()
        frame = tk.Frame(self.root, bg="#1a1a1a")
        frame.pack(expand=True)
        
        tk.Label(frame, text="ACEest Login", font=("Arial", 24), fg="#d4af37", bg="#1a1a1a").pack(pady=20)
        
        tk.Label(frame, text="Username", fg="white", bg="#1a1a1a").pack(pady=5)
        self.username_var = tk.StringVar()
        tk.Entry(frame, textvariable=self.username_var, bg="#333", fg="white").pack()
        
        tk.Label(frame, text="Password", fg="white", bg="#1a1a1a").pack(pady=5)
        self.password_var = tk.StringVar()
        tk.Entry(frame, textvariable=self.password_var, show="*", bg="#333", fg="white").pack()
        
        ttk.Button(frame, text="Login", command=self.login).pack(pady=20)
    
    def login(self):
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        self.cur.execute("SELECT role FROM users WHERE username=? AND password=?", (username,password))
        row = self.cur.fetchone()
        if row:
            self.current_user = username
            self.current_role = row[0]
            self.dashboard()
        else:
            messagebox.showerror("Login Failed", "Invalid credentials")
    
    # ---------- DASHBOARD ----------
    def dashboard(self):
        self.clear_root()
        
        # Header
        header = tk.Label(self.root, text=f"ACEest Dashboard ({self.current_role})", font=("Arial", 24, "bold"), bg="#d4af37", fg="black", height=2)
        header.pack(fill="x")
        
        # Left panel: Clients & program generator
        left = tk.Frame(self.root, bg="#1a1a1a", width=350)
        left.pack(side="left", fill="y", padx=10, pady=10)
        
        # Client selection
        tk.Label(left, text="Select Client", bg="#1a1a1a", fg="white").pack(pady=(5,0))
        self.client_list = ttk.Combobox(left, state="readonly")
        self.client_list.pack()
        self.client_list.bind("<<ComboboxSelected>>", self.load_client)
        self.refresh_client_list()
        
        ttk.Button(left, text="Add / Save Client", command=self.add_save_client).pack(pady=5)
        ttk.Button(left, text="Generate AI Program", command=self.generate_program).pack(pady=5)
        ttk.Button(left, text="Generate PDF Report", command=self.generate_pdf).pack(pady=5)
        
        # Membership Billing
        ttk.Button(left, text="Check Membership", command=self.check_membership).pack(pady=5)
        
        # Right panel: Notebook with charts and workouts
        right = tk.Frame(self.root, bg="#1a1a1a")
        right.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        
        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True)
        
        # Tab1: Summary & charts
        self.tab_summary = tk.Frame(self.notebook, bg="#1a1a1a")
        self.notebook.add(self.tab_summary, text="Client Summary")
        
        self.summary_text = tk.Text(self.tab_summary, bg="#111", fg="white", font=("Consolas", 11))
        self.summary_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Chart placeholder
        self.chart_frame = tk.Frame(self.tab_summary, bg="#1a1a1a")
        self.chart_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Tab2: Workouts & exercises
        self.tab_workouts = tk.Frame(self.notebook, bg="#1a1a1a")
        self.notebook.add(self.tab_workouts, text="Workouts & Exercises")
        self.setup_workout_tab()
    
    # ---------- CLIENT MANAGEMENT ----------
    def refresh_client_list(self):
        self.cur.execute("SELECT name FROM clients ORDER BY name")
        names = [row[0] for row in self.cur.fetchall()]
        self.client_list["values"] = names
    
    def add_save_client(self):
        name = tk.simpledialog.askstring("Client Name", "Enter client name:")
        if not name:
            return
        self.cur.execute("INSERT OR IGNORE INTO clients (name,membership_status) VALUES (?,?)",(name,"Active"))
        self.conn.commit()
        self.refresh_client_list()
        messagebox.showinfo("Saved", f"Client {name} saved")
    
    def load_client(self, event=None):
        name = self.client_list.get()
        if not name:
            return
        self.current_client = name
        self.refresh_summary()
        self.refresh_workouts()
        self.plot_charts()
    
    # ---------- AI-STYLE PROGRAM GENERATOR ----------
    def generate_program(self):
        if not self.current_client:
            messagebox.showwarning("No Client", "Select a client first")
            return
        program_type = random.choice(list(self.program_templates.keys()))
        program_detail = random.choice(self.program_templates[program_type])
        self.cur.execute("UPDATE clients SET program=? WHERE name=?",(program_detail,self.current_client))
        self.conn.commit()
        messagebox.showinfo("Program Generated", f"Program for {self.current_client}: {program_detail}")
        self.refresh_summary()
    
    # ---------- PDF REPORT ----------
    def generate_pdf(self):
        if not self.current_client:
            messagebox.showwarning("No Client", "Select a client first")
            return
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial","B",16)
        pdf.cell(0,10,f"ACEest Client Report - {self.current_client}",ln=True)
        self.cur.execute("SELECT * FROM clients WHERE name=?",(self.current_client,))
        client = self.cur.fetchone()
        pdf.set_font("Arial","",12)
        for i,col in enumerate(["ID","Name","Age","Height","Weight","Program","Calories","Target Weight","Target Adherence","Membership","End"]):
            pdf.cell(0,10,f"{col}: {client[i]}",ln=True)
        pdf.output(f"{self.current_client}_report.pdf")
        messagebox.showinfo("PDF Generated", f"{self.current_client}_report.pdf created")
    
    # ---------- MEMBERSHIP ----------
    def check_membership(self):
        if not self.current_client:
            return
        self.cur.execute("SELECT membership_status,membership_end FROM clients WHERE name=?",(self.current_client,))
        status,end = self.cur.fetchone()
        msg = f"Membership: {status}\nRenewal Date: {end if end else 'N/A'}"
        messagebox.showinfo("Membership", msg)
    
    # ---------- SUMMARY & CHARTS ----------
    def refresh_summary(self):
        if not self.current_client:
            return
        self.cur.execute("SELECT * FROM clients WHERE name=?",(self.current_client,))
        client = self.cur.fetchone()
        text = f"Name: {client[1]}\nProgram: {client[5]}\nCalories: {client[6]}\nMembership: {client[9]}"
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0","end")
        self.summary_text.insert("end",text)
        self.summary_text.configure(state="disabled")
    
    def plot_charts(self):
        for widget in self.chart_frame.winfo_children():
            widget.destroy()
        if not self.current_client:
            return
        self.cur.execute("SELECT week, adherence FROM progress WHERE client_name=? ORDER BY id",(self.current_client,))
        data = self.cur.fetchall()
        if not data:
            return
        weeks = [d[0] for d in data]
        adherence = [d[1] for d in data]
        fig, ax = plt.subplots(figsize=(6,3))
        ax.plot(weeks,adherence,marker="o")
        ax.set_title("Weekly Adherence")
        ax.set_ylabel("%")
        ax.set_ylim(0,100)
        ax.grid(True)
        canvas = FigureCanvasTkAgg(fig,self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both",expand=True)
    
    # ---------- WORKOUT + EXERCISE TAB ----------
    def setup_workout_tab(self):
        # Treeview
        columns = ("date","type","duration","notes")
        self.tree_workouts = ttk.Treeview(self.tab_workouts, columns=columns, show="headings")
        for c in columns:
            self.tree_workouts.heading(c,c.title())
            self.tree_workouts.column(c,width=150)
        self.tree_workouts.pack(fill="both",expand=True)
        ttk.Button(self.tab_workouts,text="Add Workout",command=self.add_workout).pack(pady=5)
    
    def refresh_workouts(self):
        for row in self.tree_workouts.get_children():
            self.tree_workouts.delete(row)
        if not self.current_client:
            return
        self.cur.execute("SELECT date,workout_type,duration_min,notes FROM workouts WHERE client_name=? ORDER BY date DESC",(self.current_client,))
        rows = self.cur.fetchall()
        for r in rows:
            self.tree_workouts.insert("", "end", values=r)
    
    def add_workout(self):
        if not self.current_client:
            return
        win = tk.Toplevel(self.root)
        win.title(f"Add Workout - {self.current_client}")
        win.geometry("400x400")
        tk.Label(win,text="Date (YYYY-MM-DD)").pack()
        date_var = tk.StringVar(value=date.today().isoformat())
        tk.Entry(win,textvariable=date_var).pack()
        tk.Label(win,text="Type").pack()
        type_var = tk.StringVar()
        ttk.Combobox(win,textvariable=type_var,values=["Strength","Hypertrophy","Cardio","Mobility"],state="readonly").pack()
        tk.Label(win,text="Duration (min)").pack()
        dur_var = tk.IntVar(value=60)
        tk.Entry(win,textvariable=dur_var).pack()
        tk.Label(win,text="Notes").pack()
        notes_var = tk.StringVar()
        tk.Entry(win,textvariable=notes_var).pack()
        def save():
            self.cur.execute("INSERT INTO workouts (client_name,date,workout_type,duration_min,notes) VALUES (?,?,?,?,?)",
                             (self.current_client,date_var.get(),type_var.get(),dur_var.get(),notes_var.get()))
            self.conn.commit()
            self.refresh_workouts()
            win.destroy()
        ttk.Button(win,text="Save",command=save).pack(pady=10)
    
    # ---------- UTILITY ----------
    def clear_root(self):
        for widget in self.root.winfo_children():
            widget.destroy()

# ---------- RUN ----------
if __name__ == "__main__":
    init_db()
    root = tk.Tk()
    app = ACEestApp(root)
    root.mainloop()
