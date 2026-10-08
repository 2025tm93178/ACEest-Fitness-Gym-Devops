# ACEestFull.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import sqlite3
from datetime import datetime, date
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from fpdf import FPDF
import random

DB_NAME = "aceest_fitness.db"


class ACEestApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ACEest Fitness & Performance")
        self.root.geometry("1400x900")
        self.root.configure(bg="#1a1a1a")

        self.conn = None
        self.cur = None
        self.current_client = None
        self.current_user = None
        self.user_role = None

        self.init_db()
        self.setup_data()
        self.show_login_window()

    # ---------- DATABASE ----------

    def init_db(self):
        self.conn = sqlite3.connect(DB_NAME)
        self.cur = self.conn.cursor()

        # Users table
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                role TEXT
            )
            """
        )
        # Default admin user
        self.cur.execute(
            "INSERT OR IGNORE INTO users (username, password, role) "
            "VALUES ('admin','admin','Admin')"
        )

        # Clients
        self.cur.execute(
            """
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
                membership_expiry TEXT
            )
            """
        )

        # Progress
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT,
                week TEXT,
                adherence INTEGER
            )
            """
        )

        # Workouts
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT,
                date TEXT,
                workout_type TEXT,
                duration_min INTEGER,
                notes TEXT
            )
            """
        )

        # Exercises
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS exercises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workout_id INTEGER,
                name TEXT,
                sets INTEGER,
                reps INTEGER,
                weight REAL
            )
            """
        )

        # Metrics
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT,
                date TEXT,
                weight REAL,
                waist REAL,
                bodyfat REAL
            )
            """
        )

        self.conn.commit()

    # ---------- DATA ----------

    def setup_data(self):
        self.programs = {
            "Fat Loss (FL) – 3 day": {"factor": 22, "desc": "3-day full-body fat loss"},
            "Fat Loss (FL) – 5 day": {"factor": 24, "desc": "5-day split, higher volume fat loss"},
            "Muscle Gain (MG) – PPL": {"factor": 35, "desc": "Push/Pull/Legs hypertrophy"},
            "Beginner (BG)": {"factor": 26, "desc": "3-day simple beginner full-body"},
        }

    # ---------- LOGIN ----------

    def show_login_window(self):
        # Root is already created; show login as modal Toplevel
        self.root.withdraw()  # hide main until login success

        self.login_win = tk.Toplevel(self.root)
        self.login_win.title("Login")
        self.login_win.geometry("300x200")
        self.login_win.configure(bg="#1a1a1a")
        self.login_win.protocol("WM_DELETE_WINDOW", self.on_login_close)

        tk.Label(self.login_win, text="Username", bg="#1a1a1a", fg="white").pack(pady=(20, 5))
        self.username_var = tk.StringVar()
        tk.Entry(self.login_win, textvariable=self.username_var).pack()

        tk.Label(self.login_win, text="Password", bg="#1a1a1a", fg="white").pack(pady=(10, 5))
        self.password_var = tk.StringVar()
        tk.Entry(self.login_win, textvariable=self.password_var, show="*").pack()

        ttk.Button(self.login_win, text="Login", command=self.login_user).pack(pady=20)

        # Make login modal
        self.login_win.transient(self.root)
        self.login_win.grab_set()
        self.login_win.focus_set()

    def on_login_close(self):
        # If user closes login window, exit app
        self.root.destroy()

    def login_user(self):
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        self.cur.execute(
            "SELECT role FROM users WHERE username=? AND password=?",
            (username, password),
        )
        row = self.cur.fetchone()
        if row:
            self.user_role = row[0]
            self.current_user = username
            self.login_win.grab_release()
            self.login_win.destroy()
            self.root.deiconify()  # show main window
            self.setup_ui()
        else:
            messagebox.showerror("Login Failed", "Invalid credentials\nTry admin / admin")

    # ---------- UI ----------

    def setup_ui(self):
        # Header
        header = tk.Label(
            self.root,
            text=f"ACEest Fitness Dashboard ({self.user_role})",
            bg="#d4af37",
            fg="black",
            font=("Helvetica", 24, "bold"),
            height=2,
        )
        header.pack(fill="x")

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Label(
            self.root,
            textvariable=self.status_var,
            bg="#111111",
            fg="#d4af37",
            anchor="w",
        )
        status_bar.pack(side="bottom", fill="x")

        # Main area
        main = tk.Frame(self.root, bg="#1a1a1a")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # LEFT PANEL (client management)
        left = tk.LabelFrame(
            main,
            text=" Client Management ",
            bg="#1a1a1a",
            fg="#d4af37",
            font=("Arial", 12, "bold"),
        )
        left.pack(side="left", fill="y", padx=10, pady=5)

        tk.Label(left, text="Select Client", bg="#1a1a1a", fg="white").pack(pady=(5, 0))
        self.client_list = ttk.Combobox(left, state="readonly")
        self.client_list.pack(pady=(0, 5))
        self.client_list.bind("<<ComboboxSelected>>", self.on_client_selected)

        tk.Label(left, text="Name", bg="#1a1a1a", fg="white").pack(pady=(5, 0))
        self.name = tk.StringVar()
        tk.Entry(left, textvariable=self.name, bg="#333", fg="white").pack()

        tk.Label(left, text="Age", bg="#1a1a1a", fg="white").pack(pady=(5, 0))
        self.age = tk.IntVar()
        tk.Entry(left, textvariable=self.age, bg="#333", fg="white").pack()

        tk.Label(left, text="Height (cm)", bg="#1a1a1a", fg="white").pack(pady=(5, 0))
        self.height = tk.DoubleVar()
        tk.Entry(left, textvariable=self.height, bg="#333", fg="white").pack()

        tk.Label(left, text="Weight (kg)", bg="#1a1a1a", fg="white").pack(pady=(5, 0))
        self.weight = tk.DoubleVar()
        tk.Entry(left, textvariable=self.weight, bg="#333", fg="white").pack()

        tk.Label(left, text="Program", bg="#1a1a1a", fg="white").pack(pady=(5, 0))
        self.program = tk.StringVar()
        ttk.Combobox(
            left,
            textvariable=self.program,
            values=list(self.programs.keys()),
            state="readonly",
        ).pack()

        # Membership expiry
        tk.Label(
            left,
            text="Membership Expiry (YYYY-MM-DD)",
            bg="#1a1a1a",
            fg="white",
        ).pack(pady=(10, 0))
        self.membership_var = tk.StringVar()
        tk.Entry(left, textvariable=self.membership_var, bg="#333", fg="white").pack()

        # Buttons
        ttk.Button(left, text="Save Client", command=self.save_client).pack(pady=5)
        ttk.Button(left, text="Load Client", command=self.load_client).pack(pady=5)
        ttk.Button(left, text="Generate AI Program", command=self.generate_ai_program).pack(
            pady=5
        )
        ttk.Button(left, text="Export PDF Report", command=self.export_pdf_report).pack(
            pady=5
        )

        # RIGHT PANEL (notebook for charts & program)
        right = tk.Frame(main, bg="#1a1a1a")
        right.pack(side="right", fill="both", expand=True, padx=5, pady=5)

        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True)

        # Summary tab
        summary_frame = tk.Frame(notebook, bg="#1a1a1a")
        notebook.add(summary_frame, text="Client Summary")
        self.summary = tk.Text(summary_frame, bg="#111", fg="white", font=("Consolas", 11))
        self.summary.pack(fill="both", expand=True, padx=10, pady=10)

        # Analytics tab
        analytics_frame = tk.Frame(notebook, bg="#1a1a1a")
        notebook.add(analytics_frame, text="Progress & Analytics")

        # Embedded Chart placeholder (currently empty)
        self.fig, self.ax = plt.subplots(figsize=(6, 4))
        self.canvas = FigureCanvasTkAgg(self.fig, master=analytics_frame)
        self.canvas.get_tk_widget().pack(pady=10, fill="both", expand=True)

        # Treeview for AI program
        self.program_tree = ttk.Treeview(
            analytics_frame,
            columns=("day", "exercise", "sets", "reps"),
            show="headings",
        )
        for col in ("day", "exercise", "sets", "reps"):
            self.program_tree.heading(col, text=col.capitalize())
        self.program_tree.pack(fill="both", expand=True, pady=10)

        self.refresh_client_list()

    # ---------- CLIENT MANAGEMENT ----------

    def refresh_client_list(self):
        self.cur.execute("SELECT name FROM clients ORDER BY name")
        names = [row[0] for row in self.cur.fetchall()]
        self.client_list["values"] = names
        if self.current_client in names:
            self.client_list.set(self.current_client)

    def on_client_selected(self, event=None):
        self.current_client = self.client_list.get()
        self.load_client()

    def save_client(self):
        name = self.name.get().strip()
        if not name:
            messagebox.showerror("Error", "Name required")
            return
        program = self.program.get()
        age = self.age.get()
        height = self.height.get()
        weight = self.weight.get()
        membership = self.membership_var.get()
        factor = self.programs.get(program, {}).get("factor", 25)
        calories = int(weight * factor) if weight > 0 else None
        try:
            self.cur.execute(
                """
                INSERT OR REPLACE INTO clients
                (name, age, height, weight, program, calories, membership_expiry)
                VALUES (?,?,?,?,?,?,?)
                """,
                (name, age, height, weight, program, calories, membership),
            )
            self.conn.commit()
            self.current_client = name
            self.refresh_client_list()
            self.set_status(f"Saved client: {name}")
            messagebox.showinfo("Saved", "Client data saved")
        except Exception as e:
            messagebox.showerror("DB Error", str(e))

    def load_client(self):
        if not self.current_client:
            return
        self.cur.execute("SELECT * FROM clients WHERE name=?", (self.current_client,))
        row = self.cur.fetchone()
        if not row:
            return
        (
            _id,
            name,
            age,
            height,
            weight,
            program,
            calories,
            target_weight,
            target_adherence,
            membership_expiry,
        ) = row
        self.name.set(name)
        self.age.set(age or 0)
        self.height.set(height or 0)
        self.weight.set(weight or 0)
        self.program.set(program or "")
        self.membership_var.set(membership_expiry or "")
        self.refresh_summary()

    def set_status(self, text):
        self.status_var.set(text)

    def refresh_summary(self):
        if not self.current_client:
            return
        self.cur.execute("SELECT * FROM clients WHERE name=?", (self.current_client,))
        client = self.cur.fetchone()
        if not client:
            return
        (
            _id,
            name,
            age,
            height,
            weight,
            program,
            calories,
            target_weight,
            target_adherence,
            membership_expiry,
        ) = client
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert(
            "end",
            f"Name: {name}\n"
            f"Age: {age}\n"
            f"Height: {height} cm\n"
            f"Weight: {weight} kg\n"
            f"Program: {program}\n"
            f"Membership Expiry: {membership_expiry}",
        )
        self.summary.configure(state="disabled")

    # ---------- AI PROGRAM GENERATOR ----------

    def generate_ai_program(self):
        if not self.current_client:
            messagebox.showerror("Error", "Select client first")
            return
        exp_level = simpledialog.askstring(
            "Experience",
            "Enter experience (beginner/intermediate/advanced):",
            parent=self.root,
        )
        if not exp_level or exp_level.lower() not in ["beginner", "intermediate", "advanced"]:
            messagebox.showerror("Error", "Invalid experience level")
            return
        self.cur.execute("SELECT program FROM clients WHERE name=?", (self.current_client,))
        row = self.cur.fetchone()
        if not row:
            return
        program_name = row[0]

        exercises_pool = {
            "Strength": [
                "Squat",
                "Deadlift",
                "Bench Press",
                "Overhead Press",
                "Pull-Up",
                "Barbell Row",
            ],
            "Hypertrophy": [
                "Leg Press",
                "Incline Dumbbell Press",
                "Lat Pulldown",
                "Lateral Raise",
                "Bicep Curl",
                "Tricep Extension",
            ],
            "Conditioning": [
                "Running",
                "Cycling",
                "Rowing",
                "Burpees",
                "Jump Rope",
                "Kettlebell Swings",
            ],
            "Full Body": [
                "Push-Up",
                "Pull-Up",
                "Lunge",
                "Plank",
                "Dumbbell Row",
                "Dumbbell Press",
            ],
        }

        focus = "Full Body"
        if "Fat Loss" in program_name:
            focus = "Conditioning"
        elif "Muscle Gain" in program_name:
            focus = "Hypertrophy"

        if exp_level.lower() == "beginner":
            sets_range = (2, 3)
            reps_range = (8, 12)
            days = 3
        elif exp_level.lower() == "intermediate":
            sets_range = (3, 4)
            reps_range = (8, 15)
            days = 4
        else:
            sets_range = (4, 5)
            reps_range = (6, 15)
            days = 5

        weekly_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][:days]

        for item in self.program_tree.get_children():
            self.program_tree.delete(item)

        for day in weekly_days:
            exercises = random.sample(exercises_pool[focus], k=3 if days < 4 else 4)
            for ex in exercises:
                sets = random.randint(*sets_range)
                reps = random.randint(*reps_range)
                self.program_tree.insert("", "end", values=(day, ex, sets, reps))

        self.set_status(f"AI program generated for {self.current_client}")
        messagebox.showinfo("Generated", "AI workout program generated!")

    # ---------- PDF REPORT ----------

    def export_pdf_report(self):
        if not self.current_client:
            return
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, f"Client Report - {self.current_client}", ln=True, align="C")
        pdf.set_font("Arial", "", 12)
        self.cur.execute("SELECT * FROM clients WHERE name=?", (self.current_client,))
        row = self.cur.fetchone()
        if row:
            pdf.ln(10)
            pdf.cell(0, 10, f"Name: {row[1]}", ln=True)
            pdf.cell(0, 10, f"Age: {row[2]}", ln=True)
            pdf.cell(0, 10, f"Height: {row[3]} cm", ln=True)
            pdf.cell(0, 10, f"Weight: {row[4]} kg", ln=True)
            pdf.cell(0, 10, f"Program: {row[5]}", ln=True)
            pdf.cell(0, 10, f"Membership Expiry: {row[9]}", ln=True)
        pdf.output(f"{self.current_client}_report.pdf")
        messagebox.showinfo(
            "PDF Exported",
            f"Report saved as {self.current_client}_report.pdf",
        )


if __name__ == "__main__":
    root = tk.Tk()
    app = ACEestApp(root)
    root.mainloop()
