import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime, date
import matplotlib.pyplot as plt

DB_NAME = "aceest_fitness.db"


class ACEestApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ACEest Fitness & Performance")
        self.root.geometry("1300x850")
        self.root.configure(bg="#1a1a1a")

        self.conn = None
        self.cur = None

        self.current_client = None

        self.init_db()
        self.setup_data()
        self.setup_ui()
        self.refresh_client_list()

    # ---------- DATABASE ----------

    def init_db(self):
        self.conn = sqlite3.connect(DB_NAME)
        self.cur = self.conn.cursor()

        # Ensure clients table has the correct columns.
        # For a simple desktop app, easiest is to drop and recreate if schema is old.
        self.cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='clients'"
        )
        exists = self.cur.fetchone() is not None

        if exists:
            # Check schema
            self.cur.execute("PRAGMA table_info(clients)")
            cols = [row[1] for row in self.cur.fetchall()]
            required = {
                "id",
                "name",
                "age",
                "height",
                "weight",
                "program",
                "calories",
                "target_weight",
                "target_adherence",
            }
            if not required.issubset(set(cols)):
                # Drop and recreate with full schema
                self.cur.execute("DROP TABLE clients")

        # Create clients with full schema
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
                target_adherence INTEGER
            )
            """
        )

        # Weekly adherence
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

        # Workouts (session-level)
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

        # Exercises (per workout)
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

        # Body metrics (weight, waist, etc.)
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

    # ---------- UI ----------

    def setup_ui(self):
        # Header
        header = tk.Label(
            self.root,
            text="ACEest Functional Fitness System",
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

        # Client selection
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

        # Goals
        tk.Label(left, text="Target Weight (kg)", bg="#1a1a1a", fg="white").pack(pady=(10, 0))
        self.target_weight = tk.DoubleVar()
        tk.Entry(left, textvariable=self.target_weight, bg="#333", fg="white").pack()

        tk.Label(left, text="Target Adherence %", bg="#1a1a1a", fg="white").pack(pady=(5, 0))
        self.target_adherence = tk.IntVar()
        tk.Entry(left, textvariable=self.target_adherence, bg="#333", fg="white").pack()

        # Weekly adherence
        tk.Label(left, text="Weekly Adherence %", bg="#1a1a1a", fg="white").pack(pady=(10, 0))
        self.adherence = tk.IntVar(value=0)
        ttk.Scale(
            left,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.adherence,
        ).pack(pady=(0, 5))

        # Buttons
        ttk.Button(left, text="Save Client", command=self.save_client).pack(pady=5)
        ttk.Button(left, text="Load Client", command=self.load_client).pack(pady=5)
        ttk.Button(left, text="Save Weekly Progress", command=self.save_progress).pack(pady=5)
        ttk.Button(left, text="Log Workout", command=self.open_log_workout_window).pack(pady=5)
        ttk.Button(left, text="Log Body Metrics", command=self.open_log_metrics_window).pack(pady=5)
        ttk.Button(left, text="View Workout History", command=self.open_workout_history_window).pack(
            pady=5
        )

        # RIGHT PANEL with Notebook
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

        ttk.Button(
            analytics_frame,
            text="Adherence Chart",
            command=self.show_progress_chart,
        ).pack(pady=10)

        ttk.Button(
            analytics_frame,
            text="Weight Trend Chart",
            command=self.show_weight_chart,
        ).pack(pady=10)

        ttk.Button(
            analytics_frame,
            text="BMI & Risk Info",
            command=self.show_bmi_info,
        ).pack(pady=10)

    # ---------- CLIENT LIST / STATUS ----------

    def refresh_client_list(self):
        self.cur.execute("SELECT name FROM clients ORDER BY name")
        names = [row[0] for row in self.cur.fetchall()]
        self.client_list["values"] = names
        if self.current_client in names:
            self.client_list.set(self.current_client)

    def on_client_selected(self, event=None):
        name = self.client_list.get()
        if not name:
            return
        self.name.set(name)
        self.current_client = name
        self.load_client()

    def set_status(self, text: str):
        self.status_var.set(text)

    # ---------- CORE LOGIC ----------

    def save_client(self):
        if not self.name.get():
            messagebox.showerror("Error", "Name is required")
            return
        if not self.program.get():
            messagebox.showerror("Error", "Program is required")
            return

        name = self.name.get().strip()
        age = self.age.get() if self.age.get() > 0 else None
        height = self.height.get() if self.height.get() > 0 else None
        weight = self.weight.get() if self.weight.get() > 0 else None

        factor = self.programs[self.program.get()]["factor"]
        calories = int(weight * factor) if weight else None

        target_weight = self.target_weight.get() if self.target_weight.get() > 0 else None
        target_adherence = (
            self.target_adherence.get() if self.target_adherence.get() > 0 else None
        )

        try:
            self.cur.execute(
                """
                INSERT OR REPLACE INTO clients
                (name, age, height, weight, program, calories, target_weight, target_adherence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    age,
                    height,
                    weight,
                    self.program.get(),
                    calories,
                    target_weight,
                    target_adherence,
                ),
            )
            self.conn.commit()
            self.current_client = name
            self.refresh_client_list()
            self.set_status(f"Saved client: {name}")
            messagebox.showinfo("Saved", "Client data saved")
        except Exception as e:
            messagebox.showerror("DB Error", str(e))

    def load_client(self):
        name = self.name.get().strip()
        if not name and self.client_list.get():
            name = self.client_list.get()

        if not name:
            messagebox.showwarning("No Client", "Enter or select client name first")
            return

        self.cur.execute("SELECT * FROM clients WHERE name=?", (name,))
        row = self.cur.fetchone()

        if not row:
            messagebox.showwarning("Not Found", "Client not found")
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
        ) = row

        self.current_client = name
        self.name.set(name)
        self.age.set(age if age is not None else 0)
        self.height.set(height if height is not None else 0.0)
        self.weight.set(weight if weight is not None else 0.0)
        self.program.set(program if program else "")
        self.target_weight.set(target_weight if target_weight is not None else 0.0)
        self.target_adherence.set(target_adherence if target_adherence is not None else 0)

        self.client_list.set(name)
        self.refresh_summary()
        self.set_status(f"Loaded client: {name}")

    def refresh_summary(self):
        if not self.current_client:
            return

        name = self.current_client

        self.cur.execute("SELECT * FROM clients WHERE name=?", (name,))
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
        ) = client

        self.cur.execute(
            "SELECT COUNT(*), AVG(adherence) FROM progress WHERE client_name=?",
            (name,),
        )
        total_weeks, avg_adherence = self.cur.fetchone()
        avg_adherence = round(avg_adherence, 1) if avg_adherence is not None else 0

        self.cur.execute(
            "SELECT date, weight, waist, bodyfat FROM metrics "
            "WHERE client_name=? ORDER BY date DESC LIMIT 1",
            (name,),
        )
        last_metric = self.cur.fetchone()

        last_metric_str = "None"
        if last_metric:
            m_date, m_weight, m_waist, m_bodyfat = last_metric
            last_metric_str = (
                f"{m_date} | {m_weight} kg, Waist {m_waist} cm, "
                f"Bodyfat {m_bodyfat}%"
            )

        goal_summary = "None"
        if target_weight or target_adherence:
            goal_summary = ""
            if target_weight:
                goal_summary += f"Target Weight: {target_weight} kg; "
            if target_adherence:
                goal_summary += f"Target Adherence: {target_adherence}%"

        prog_desc = self.programs.get(program, {}).get("desc", "")

        text = []
        text.append("CLIENT PROFILE")
        text.append("--------------")
        text.append(f"Name      : {name}")
        text.append(f"Age       : {age if age is not None else '-'}")
        text.append(f"Height    : {height if height is not None else '-'} cm")
        text.append(f"Weight    : {weight if weight is not None else '-'} kg")
        text.append(f"Program   : {program}")
        text.append(f"Calories  : {calories if calories is not None else '-'} kcal/day")
        text.append("")
        text.append("PROGRAM NOTES")
        text.append("-------------")
        text.append(f"{prog_desc}")
        text.append("")
        text.append("GOALS")
        text.append("-----")
        text.append(goal_summary)
        text.append("")
        text.append("PROGRESS SUMMARY")
        text.append("----------------")
        text.append(f"Weeks logged       : {total_weeks}")
        text.append(f"Average adherence  : {avg_adherence}%")
        text.append("")
        text.append("LAST BODY METRICS")
        text.append("-----------------")
        text.append(last_metric_str)

        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("end", "\n".join(text))
        self.summary.configure(state="disabled")

    def save_progress(self):
        if not self.name.get().strip():
            messagebox.showwarning("No Client", "Enter client name first")
            return

        week = datetime.now().strftime("Week %U - %Y")
        self.cur.execute(
            """
            INSERT INTO progress (client_name, week, adherence)
            VALUES (?, ?, ?)
            """,
            (self.name.get().strip(), week, int(self.adherence.get())),
        )
        self.conn.commit()
        self.current_client = self.name.get().strip()
        self.refresh_summary()
        self.set_status(f"Saved weekly progress for {self.current_client}")
        messagebox.showinfo("Progress Saved", "Weekly progress logged")

    # ---------- CHARTS / ANALYTICS ----------

    def show_progress_chart(self):
        if not self.ensure_client():
            return

        self.cur.execute(
            """
            SELECT week, adherence
            FROM progress
            WHERE client_name=?
            ORDER BY id
            """,
            (self.current_client,),
        )
        data = self.cur.fetchall()

        if not data:
            messagebox.showinfo("No Data", "No progress data available for this client")
            return

        weeks = [row[0] for row in data]
        adherence = [row[1] for row in data]

        plt.figure(figsize=(8, 4))
        plt.plot(weeks, adherence, marker="o", linewidth=2)
        plt.title(f"Weekly Adherence – {self.current_client}")
        plt.xlabel("Week")
        plt.ylabel("Adherence (%)")
        plt.ylim(0, 100)
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()

    def show_weight_chart(self):
        if not self.ensure_client():
            return

        self.cur.execute(
            """
            SELECT date, weight
            FROM metrics
            WHERE client_name=? AND weight IS NOT NULL
            ORDER BY date
            """,
            (self.current_client,),
        )
        data = self.cur.fetchall()

        if not data:
            messagebox.showinfo("No Data", "No weight metrics available for this client")
            return

        dates = [row[0] for row in data]
        weights = [row[1] for row in data]

        plt.figure(figsize=(8, 4))
        plt.plot(dates, weights, marker="o", linewidth=2, color="orange")
        plt.title(f"Weight Trend – {self.current_client}")
        plt.xlabel("Date")
        plt.ylabel("Weight (kg)")
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()

    def show_bmi_info(self):
        if not self.ensure_client():
            return

        height = self.height.get()
        weight = self.weight.get()

        if height <= 0 or weight <= 0:
            messagebox.showwarning("Missing Data", "Enter valid height and weight first")
            return

        h_m = height / 100.0
        bmi = weight / (h_m * h_m)
        bmi = round(bmi, 1)

        if bmi < 18.5:
            category = "Underweight"
            risk = "Potential nutrient deficiency, low energy."
        elif bmi < 25:
            category = "Normal"
            risk = "Low risk if active and strong."
        elif bmi < 30:
            category = "Overweight"
            risk = "Moderate risk; focus on adherence and progressive activity."
        else:
            category = "Obese"
            risk = "Higher risk; prioritize fat loss, consistency, and supervision."

        messagebox.showinfo(
            "BMI Info",
            f"BMI for {self.current_client}: {bmi} ({category})\n\nRisk note: {risk}",
        )

    # ---------- WORKOUT LOGGING ----------

    def ensure_client(self) -> bool:
        name = self.current_client or self.name.get().strip() or self.client_list.get()
        if not name:
            messagebox.showwarning("No Client", "Select or enter client first")
            return False
        self.current_client = name
        return True

    def open_log_workout_window(self):
        if not self.ensure_client():
            return

        win = tk.Toplevel(self.root)
        win.title(f"Log Workout – {self.current_client}")
        win.configure(bg="#1a1a1a")
        win.geometry("450x500")

        tk.Label(win, text="Date (YYYY-MM-DD)", bg="#1a1a1a", fg="white").pack(pady=(10, 0))
        date_var = tk.StringVar(value=date.today().isoformat())
        tk.Entry(win, textvariable=date_var, bg="#333", fg="white").pack()

        tk.Label(win, text="Workout Type", bg="#1a1a1a", fg="white").pack(pady=(10, 0))
        type_var = tk.StringVar()
        ttk.Combobox(
            win,
            textvariable=type_var,
            values=["Strength", "Hypertrophy", "Conditioning", "Mixed", "Mobility"],
            state="readonly",
        ).pack()

        tk.Label(win, text="Duration (min)", bg="#1a1a1a", fg="white").pack(pady=(10, 0))
        dur_var = tk.IntVar(value=60)
        tk.Entry(win, textvariable=dur_var, bg="#333", fg="white").pack()

        tk.Label(win, text="Notes", bg="#1a1a1a", fg="white").pack(pady=(10, 0))
        notes_text = tk.Text(win, height=4, bg="#333", fg="white")
        notes_text.pack(fill="x", padx=10)

        tk.Label(win, text="Exercise Name", bg="#1a1a1a", fg="white").pack(pady=(10, 0))
        ex_name_var = tk.StringVar()
        tk.Entry(win, textvariable=ex_name_var, bg="#333", fg="white").pack()

        tk.Label(win, text="Sets", bg="#1a1a1a", fg="white").pack(pady=(5, 0))
        sets_var = tk.IntVar(value=3)
        tk.Entry(win, textvariable=sets_var, bg="#333", fg="white").pack()

        tk.Label(win, text="Reps", bg="#1a1a1a", fg="white").pack(pady=(5, 0))
        reps_var = tk.IntVar(value=10)
        tk.Entry(win, textvariable=reps_var, bg="#333", fg="white").pack()

        tk.Label(win, text="Weight (kg)", bg="#1a1a1a", fg="white").pack(pady=(5, 0))
        ex_weight_var = tk.DoubleVar(value=0.0)
        tk.Entry(win, textvariable=ex_weight_var, bg="#333", fg="white").pack()

        def save_workout():
            try:
                w_date = date_var.get().strip()
                w_type = type_var.get().strip()
                duration = int(dur_var.get())
                notes = notes_text.get("1.0", "end").strip()

                if not w_date or not w_type:
                    messagebox.showerror("Error", "Date and workout type are required")
                    return

                self.cur.execute(
                    """
                    INSERT INTO workouts (client_name, date, workout_type, duration_min, notes)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (self.current_client, w_date, w_type, duration, notes),
                )
                workout_id = self.cur.lastrowid

                ex_name = ex_name_var.get().strip()
                ex_sets = sets_var.get()
                ex_reps = reps_var.get()
                ex_weight = ex_weight_var.get()

                if ex_name:
                    self.cur.execute(
                        """
                        INSERT INTO exercises (workout_id, name, sets, reps, weight)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (workout_id, ex_name, ex_sets, ex_reps, ex_weight),
                    )

                self.conn.commit()
                self.set_status(f"Workout logged for {self.current_client}")
                messagebox.showinfo("Saved", "Workout logged successfully")
                win.destroy()
            except Exception as e:
                messagebox.showerror("Error", str(e))

        ttk.Button(win, text="Save Workout", command=save_workout).pack(pady=15)

    def open_log_metrics_window(self):
        if not self.ensure_client():
            return

        win = tk.Toplevel(self.root)
        win.title(f"Log Body Metrics – {self.current_client}")
        win.configure(bg="#1a1a1a")
        win.geometry("350x300")

        tk.Label(win, text="Date (YYYY-MM-DD)", bg="#1a1a1a", fg="white").pack(pady=(10, 0))
        date_var = tk.StringVar(value=date.today().isoformat())
        tk.Entry(win, textvariable=date_var, bg="#333", fg="white").pack()

        tk.Label(win, text="Weight (kg)", bg="#1a1a1a", fg="white").pack(pady=(10, 0))
        weight_var = tk.DoubleVar(value=self.weight.get() if self.weight.get() > 0 else 0.0)
        tk.Entry(win, textvariable=weight_var, bg="#333", fg="white").pack()

        tk.Label(win, text="Waist (cm)", bg="#1a1a1a", fg="white").pack(pady=(10, 0))
        waist_var = tk.DoubleVar(value=0.0)
        tk.Entry(win, textvariable=waist_var, bg="#333", fg="white").pack()

        tk.Label(win, text="Bodyfat (%)", bg="#1a1a1a", fg="white").pack(pady=(10, 0))
        bf_var = tk.DoubleVar(value=0.0)
        tk.Entry(win, textvariable=bf_var, bg="#333", fg="white").pack()

        def save_metrics():
            try:
                m_date = date_var.get().strip()
                m_weight = weight_var.get()
                m_waist = waist_var.get()
                m_bf = bf_var.get()

                if not m_date:
                    messagebox.showerror("Error", "Date is required")
                    return

                self.cur.execute(
                    """
                    INSERT INTO metrics (client_name, date, weight, waist, bodyfat)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (self.current_client, m_date, m_weight, m_waist, m_bf),
                )
                self.conn.commit()
                if m_weight > 0:
                    self.weight.set(m_weight)
                self.refresh_summary()
                self.set_status(f"Metrics logged for {self.current_client}")
                messagebox.showinfo("Saved", "Metrics logged successfully")
                win.destroy()
            except Exception as e:
                messagebox.showerror("Error", str(e))

        ttk.Button(win, text="Save Metrics", command=save_metrics).pack(pady=15)

    # ---------- WORKOUT HISTORY (TREEVIEW) ----------

    def open_workout_history_window(self):
        if not self.ensure_client():
            return

        win = tk.Toplevel(self.root)
        win.title(f"Workout History – {self.current_client}")
        win.geometry("700x400")

        columns = ("date", "type", "duration", "notes")
        tree = ttk.Treeview(win, columns=columns, show="headings")
        tree.heading("date", text="Date")
        tree.heading("type", text="Type")
        tree.heading("duration", text="Duration (min)")
        tree.heading("notes", text="Notes")

        tree.column("date", width=100, anchor="center")
        tree.column("type", width=100, anchor="center")
        tree.column("duration", width=120, anchor="center")
        tree.column("notes", width=350, anchor="w")

        tree.pack(fill="both", expand=True)

        self.cur.execute(
            """
            SELECT date, workout_type, duration_min, notes
            FROM workouts
            WHERE client_name=?
            ORDER BY date DESC, id DESC
            """,
            (self.current_client,),
        )
        rows = self.cur.fetchall()

        for row in rows:
            tree.insert("", "end", values=row)

        self.set_status(f"Loaded workout history for {self.current_client}")


if __name__ == "__main__":
    root = tk.Tk()
    app = ACEestApp(root)
    root.mainloop()
