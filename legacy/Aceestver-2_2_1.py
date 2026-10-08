import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime
import matplotlib.pyplot as plt

DB_NAME = "aceest_fitness.db"

class ACEestApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ACEest Fitness & Performance")
        self.root.geometry("1200x800")
        self.root.configure(bg="#1a1a1a")

        self.init_db()
        self.setup_data()
        self.setup_ui()

    def init_db(self):
        self.conn = sqlite3.connect("aceest_fitness.db")
        self.cur = self.conn.cursor()

        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                age INTEGER,
                weight REAL,
                program TEXT,
                calories INTEGER
            )
        """)

        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT,
                week TEXT,
                adherence INTEGER
            )
        """)

        self.conn.commit()

    def setup_data(self):
        self.programs = {
            "Fat Loss (FL)": {"factor": 22},
            "Muscle Gain (MG)": {"factor": 35},
            "Beginner (BG)": {"factor": 26}
        }

    def setup_ui(self):
        header = tk.Label(
            self.root,
            text="ACEest Functional Fitness System",
            bg="#d4af37",
            fg="black",
            font=("Helvetica", 24, "bold"),
            height=2
        )
        header.pack(fill="x")

        main = tk.Frame(self.root, bg="#1a1a1a")
        main.pack(fill="both", expand=True, padx=20, pady=20)

        # LEFT PANEL
        left = tk.LabelFrame(main, text=" Client Management ",
                             bg="#1a1a1a", fg="#d4af37", font=("Arial", 12, "bold"))
        left.pack(side="left", fill="y", padx=10)

        self.name = tk.StringVar()
        self.age = tk.IntVar()
        self.weight = tk.DoubleVar()
        self.program = tk.StringVar()
        self.adherence = tk.IntVar(value=0)

        self._field(left, "Name", self.name)
        self._field(left, "Age", self.age)
        self._field(left, "Weight (kg)", self.weight)

        tk.Label(left, text="Program", bg="#1a1a1a", fg="white").pack(pady=5)
        ttk.Combobox(left, textvariable=self.program,
                     values=list(self.programs.keys()),
                     state="readonly").pack()

        tk.Label(left, text="Weekly Adherence %", bg="#1a1a1a", fg="white").pack(pady=10)
        ttk.Scale(left, from_=0, to=100,
                  orient="horizontal", variable=self.adherence).pack()

        ttk.Button(left, text="Save Client", command=self.save_client).pack(pady=10)
        ttk.Button(left, text="Load Client", command=self.load_client).pack(pady=5)
        ttk.Button(left, text="Save Progress", command=self.save_progress).pack(pady=5)
        ttk.Button(left, text="View Progress Chart", command=self.show_progress_chart).pack(pady=10)

        # RIGHT PANEL
        right = tk.LabelFrame(main, text=" Client Summary ",
                              bg="#1a1a1a", fg="#d4af37", font=("Arial", 12))
        right.pack(side="right", fill="both", expand=True)

        self.summary = tk.Text(right, bg="#111", fg="white", font=("Consolas", 11))
        self.summary.pack(fill="both", expand=True, padx=10, pady=10)

    def _field(self, parent, label, var):
        tk.Label(parent, text=label, bg="#1a1a1a", fg="white").pack(pady=5)
        tk.Entry(parent, textvariable=var, bg="#333", fg="white").pack()

    def save_client(self):
        if not self.name.get() or not self.program.get():
            messagebox.showerror("Error", "Name and Program required")
            return

        calories = int(self.weight.get() * self.programs[self.program.get()]["factor"])

        try:
            self.cur.execute("""
                INSERT OR REPLACE INTO clients
                (name, age, weight, program, calories)
                VALUES (?, ?, ?, ?, ?)
            """, (self.name.get(), self.age.get(),
                  self.weight.get(), self.program.get(), calories))
            self.conn.commit()
            messagebox.showinfo("Saved", "Client data saved")
        except Exception as e:
            messagebox.showerror("DB Error", str(e))

    def load_client(self):
        self.cur.execute("SELECT * FROM clients WHERE name=?", (self.name.get(),))
        row = self.cur.fetchone()

        if not row:
            messagebox.showwarning("Not Found", "Client not found")
            return

        _, name, age, weight, program, calories = row
        self.age.set(age)
        self.weight.set(weight)
        self.program.set(program)

        self.summary.delete("1.0", "end")
        self.summary.insert("end", f"""
CLIENT PROFILE
--------------
Name      : {name}
Age       : {age}
Weight    : {weight} kg
Program   : {program}
Calories  : {calories} kcal/day
        """)

    def save_progress(self):
        week = datetime.now().strftime("Week %U - %Y")
        self.cur.execute("""
            INSERT INTO progress (client_name, week, adherence)
            VALUES (?, ?, ?)
        """, (self.name.get(), week, self.adherence.get()))
        self.conn.commit()
        messagebox.showinfo("Progress Saved", "Weekly progress logged")

    def show_progress_chart(self):
        if not self.name.get():
            messagebox.showwarning("No Client", "Enter client name first")
            return

        self.cur.execute("""
            SELECT week, adherence
            FROM progress
            WHERE client_name=?
            ORDER BY id
        """, (self.name.get(),))

        data = self.cur.fetchall()

        if not data:
            messagebox.showinfo("No Data", "No progress data available for this client")
            return

        weeks = [row[0] for row in data]
        adherence = [row[1] for row in data]

        plt.figure(figsize=(8, 4))
        plt.plot(weeks, adherence, marker="o", linewidth=2)
        plt.title(f"Weekly Adherence Progress – {self.name.get()}")
        plt.xlabel("Week")
        plt.ylabel("Adherence (%)")
        plt.ylim(0, 100)
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()

if __name__ == "__main__":
    root = tk.Tk()
    app = ACEestApp(root)
    root.mainloop()
