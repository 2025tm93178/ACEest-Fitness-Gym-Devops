import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import csv

class ACEestApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ACEest Fitness & Performance")
        self.root.geometry("1250x820")
        self.root.configure(bg="#1a1a1a")

        self.clients = []  # store multiple clients

        self.programs = {
            "Fat Loss (FL)": {"workout": "Back Squat, Cardio, Bench, Deadlift, Recovery",
                              "diet": "Egg Whites, Chicken, Fish Curry",
                              "color": "#e74c3c", "calorie_factor": 22},
            "Muscle Gain (MG)": {"workout": "Squat, Bench, Deadlift, Press, Rows",
                                 "diet": "Eggs, Biryani, Mutton Curry",
                                 "color": "#2ecc71", "calorie_factor": 35},
            "Beginner (BG)": {"workout": "Air Squats, Ring Rows, Push-ups",
                              "diet": "Balanced Tamil Meals",
                              "color": "#3498db", "calorie_factor": 26}
        }

        self.setup_ui()

    def setup_ui(self):
        header = tk.Frame(self.root, bg="#d4af37", height=80)
        header.pack(fill="x")
        tk.Label(header, text="ACEest FUNCTIONAL FITNESS SYSTEM v2",
                 font=("Helvetica", 24, "bold"), bg="#d4af37", fg="black").pack(pady=20)

        main = tk.Frame(self.root, bg="#1a1a1a")
        main.pack(fill="both", expand=True, padx=20, pady=20)

        # LEFT PANEL – CLIENT PROFILE
        left = tk.LabelFrame(main, text=" Client Profile ", bg="#1a1a1a",
                             fg="#d4af37", font=("Arial", 12, "bold"))
        left.pack(side="left", fill="y", padx=10)

        self.name_var = tk.StringVar()
        self.age_var = tk.IntVar()
        self.weight_var = tk.DoubleVar()
        self.program_var = tk.StringVar()
        self.progress_var = tk.IntVar(value=0)
        self.notes_var = tk.StringVar()

        self._input(left, "Name", self.name_var)
        self._input(left, "Age", self.age_var)
        self._input(left, "Weight (kg)", self.weight_var)

        tk.Label(left, text="Program", bg="#1a1a1a", fg="white").pack(pady=5)
        self.program_box = ttk.Combobox(left, textvariable=self.program_var,
                                        values=list(self.programs.keys()), state="readonly")
        self.program_box.pack(padx=20)
        self.program_box.bind("<<ComboboxSelected>>", self.update_program)

        tk.Label(left, text="Weekly Adherence (%)", bg="#1a1a1a", fg="white").pack(pady=10)
        ttk.Scale(left, from_=0, to=100, variable=self.progress_var, orient="horizontal").pack(padx=20)

        tk.Label(left, text="Coach Notes", bg="#1a1a1a", fg="white").pack(pady=5)
        tk.Entry(left, textvariable=self.notes_var, bg="#333", fg="white").pack(padx=20)

        ttk.Button(left, text="Save Client", command=self.save_client).pack(pady=15)
        ttk.Button(left, text="Export CSV", command=self.export_csv).pack(pady=5)
        ttk.Button(left, text="Reset", command=self.reset).pack()

        # RIGHT PANEL – PROGRAM DETAILS
        right = tk.Frame(main, bg="#1a1a1a")
        right.pack(side="right", fill="both", expand=True)

        self.workout_text = self._scrollable_block(right, " Weekly Training Plan ")
        self.diet_text = self._scrollable_block(right, " Nutrition Plan ")

        self.calorie_label = tk.Label(right, text="Estimated Calories: --",
                                      bg="#1a1a1a", fg="#d4af37", font=("Arial", 12, "bold"))
        self.calorie_label.pack(pady=10)

        # CLIENT LIST TABLE
        table_frame = tk.LabelFrame(right, text=" Client List ", bg="#1a1a1a", fg="#d4af37")
        table_frame.pack(fill="both", expand=True, pady=10)

        self.client_table = ttk.Treeview(table_frame, columns=("Name", "Age", "Weight", "Program", "Adherence", "Notes"),
                                         show="headings", height=6)
        for col in self.client_table["columns"]:
            self.client_table.heading(col, text=col)
        self.client_table.pack(fill="both", expand=True)

        # PROGRESS CHART
        chart_frame = tk.LabelFrame(right, text=" Progress Chart ", bg="#1a1a1a", fg="#d4af37")
        chart_frame.pack(fill="both", expand=True, pady=10)

        self.fig, self.ax = plt.subplots(figsize=(4, 2))
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
        self.canvas.get_tk_widget().pack()

    def _input(self, parent, label, variable):
        tk.Label(parent, text=label, bg="#1a1a1a", fg="white").pack(pady=5)
        tk.Entry(parent, textvariable=variable, bg="#333", fg="white").pack(padx=20)

    def _scrollable_block(self, parent, title):
        frame = tk.LabelFrame(parent, text=title, bg="#1a1a1a", fg="#d4af37", font=("Arial", 12))
        frame.pack(fill="both", expand=True, pady=5)
        text = tk.Text(frame, bg="#111", fg="white", wrap="word", height=8)
        text.pack(fill="both", expand=True, padx=10, pady=10)
        text.config(state="disabled")
        return text

    def update_program(self, event=None):
        program = self.program_var.get()
        if not program: return
        data = self.programs[program]
        self._update_text(self.workout_text, data["workout"], data["color"])
        self._update_text(self.diet_text, data["diet"], "white")
        if self.weight_var.get() > 0:
            calories = int(self.weight_var.get() * data["calorie_factor"])
            self.calorie_label.config(text=f"Estimated Calories: {calories} kcal")

    def _update_text(self, widget, content, color):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", content)
        widget.config(fg=color, state="disabled")

    def save_client(self):
        if not self.name_var.get() or not self.program_var.get():
            messagebox.showwarning("Incomplete", "Please fill client name and program.")
            return
        client = (self.name_var.get(), self.age_var.get(), self.weight_var.get(),
                  self.program_var.get(), self.progress_var.get(), self.notes_var.get())
        self.clients.append(client)
        self.client_table.insert("", "end", values=client)
        self.update_chart()
        messagebox.showinfo("Saved", f"Client {self.name_var.get()} saved successfully.")

    def export_csv(self):
        if not self.clients:
            messagebox.showwarning("No Data", "No clients to export.")
            return
        file = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if file:
            with open(file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Name", "Age", "Weight", "Program", "Adherence", "Notes"])
                writer.writerows(self.clients)
            messagebox.showinfo("Exported", f"Client data exported to {file}")

    def update_chart(self):
        self.ax.clear()
        adherence = [c[4] for c in self.clients]
        names = [c[0] for c in self.clients]
        self.ax.bar(names, adherence, color="#d4af37")
        self.ax.set_ylabel("Adherence %")
        self.ax.set_title("Client Progress")
        self.canvas.draw()

    def reset(self):
        self.name_var.set("")
        self.age_var.set(0)
        self.weight_var.set(0)
        self.program_var.set("")
        self.progress_var.set(0)
        self.notes_var.set("")
        self._update_text(self.workout_text, "", "white")
        self._update_text(self.diet_text,)