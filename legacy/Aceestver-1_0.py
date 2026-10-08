import tkinter as tk
from tkinter import ttk, messagebox

class ACEestApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ACEest Fitness and Gym")
        self.root.geometry("1100x750")
        self.root.configure(bg="#1a1a1a")  # Premium Dark Theme

        # Data Store for Program Specification
        self.programs = {
            "Fat Loss (FL)": {
                "workout": "Mon: 5x5 Back Squat + AMRAP\nTue: EMOM 20min Assault Bike\nWed: Bench Press + 21-15-9\nThu: 10RFT Deadlifts/Box Jumps\nFri: 30min Active Recovery",
                "diet": "B: 3 Egg Whites + Oats Idli\nL: Grilled Chicken + Brown Rice\nD: Fish Curry + Millet Roti\nTarget: 2,000 kcal",
                "color": "#e74c3c"
            },
            "Muscle Gain (MG)": {
                "workout": "Mon: Squat 5x5\nTue: Bench 5x5\nWed: Deadlift 4x6\nThu: Front Squat 4x8\nFri: Incline Press 4x10\nSat: Barbell Rows 4x10",
                "diet": "B: 4 Eggs + PB Oats\nL: Chicken Biryani (250g Chicken)\nD: Mutton Curry + Jeera Rice\nTarget: 3,200 kcal",
                "color": "#2ecc71"
            },
            "Beginner (BG)": {
                "workout": "Circuit Training: Air Squats, Ring Rows, Push-ups.\nFocus: Technique Mastery & Form (90% Threshold)",
                "diet": "Balanced Tamil Meals: Idli-Sambar, Rice-Dal, Chapati.\nProtein: 120g/day",
                "color": "#3498db"
            }
        }

        self.setup_ui()

    def setup_ui(self):
        # Header
        header = tk.Frame(self.root, bg="#d4af37", height=80)
        header.pack(fill="x")
        tk.Label(header, text="ACEest FUNCTIONAL FITNESS", font=("Helvetica", 24, "bold"), bg="#d4af37", fg="black").pack(pady=20)

        # Main Container
        main_frame = tk.Frame(self.root, bg="#1a1a1a")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Left Panel: Client Selection
        left_panel = tk.LabelFrame(main_frame, text=" Client Profile ", fg="#d4af37", bg="#1a1a1a", font=("Arial", 12, "bold"))
        left_panel.pack(side="left", fill="y", padx=10)

        tk.Label(left_panel, text="Select Program:", bg="#1a1a1a", fg="white").pack(pady=10)
        self.prog_var = tk.StringVar()
        self.prog_menu = ttk.Combobox(left_panel, textvariable=self.prog_var, values=list(self.programs.keys()), state="readonly")
        self.prog_menu.pack(padx=20, pady=5)
        self.prog_menu.bind("<<ComboboxSelected>>", self.update_display)

        # Site Metrics Summary (Reference)
        metrics_text = "CAPACITY: 150 Users\nAREA: 10,000 sq ft\nBREAK-EVEN: 250 Members"
        tk.Label(left_panel, text=metrics_text, bg="#333", fg="#ddd", font=("Courier", 10), justify="left").pack(side="bottom", fill="x", pady=20)

        # Right Panel: Display Charts
        self.right_panel = tk.Frame(main_frame, bg="#1a1a1a")
        self.right_panel.pack(side="right", fill="both", expand=True)

        # Workout Chart Display
        self.work_frame = tk.LabelFrame(self.right_panel, text=" Weekly Workout Chart ", fg="#d4af37", bg="#1a1a1a", font=("Arial", 12))
        self.work_frame.pack(fill="both", expand=True, pady=5)
        self.work_label = tk.Label(self.work_frame, text="Select a profile to view workout", bg="#1a1a1a", fg="white", justify="left", font=("Arial", 11))
        self.work_label.pack(padx=10, pady=10)

        # Diet Chart Display
        self.diet_frame = tk.LabelFrame(self.right_panel, text=" Daily Nutrition Plan (Tamil Nadu Context) ", fg="#d4af37", bg="#1a1a1a", font=("Arial", 12))
        self.diet_frame.pack(fill="both", expand=True, pady=5)
        self.diet_label = tk.Label(self.diet_frame, text="Select a profile to view diet", bg="#1a1a1a", fg="white", justify="left", font=("Arial", 11))
        self.diet_label.pack(padx=10, pady=10)

    def update_display(self, event):
        selected = self.prog_var.get()
        data = self.programs[selected]
        
        self.work_label.config(text=data["workout"], fg=data["color"])
        self.diet_label.config(text=data["diet"])

if __name__ == "__main__":
    root = tk.Tk()
    app = ACEestApp(root)
    root.mainloop()