"""ACEest Fitness & Gym - Flask web service.

A REST port of the ACEest desktop (Tkinter) application. Pure business logic
(calories, BMI, membership, programme generation) lives in plain functions so
it can be unit tested without the HTTP layer.
"""
import csv
import io
import os
import random
import sqlite3
from datetime import date, datetime

from flask import Flask, Response, current_app, g, jsonify, request

APP_VERSION = "3.2.4"

PROGRAMS = {
    "FL": {
        "name": "Fat Loss (FL)",
        "factor": 22,
        "focus": "Conditioning",
        "workout": [
            "Mon: Back Squat 5x5 + Core",
            "Tue: EMOM 20min Assault Bike",
            "Wed: Bench Press + 21-15-9",
            "Thu: Deadlift + Box Jumps",
            "Fri: Zone 2 Cardio 30min",
        ],
        "diet": [
            "Breakfast: Egg Whites + Oats",
            "Lunch: Grilled Chicken + Brown Rice",
            "Dinner: Fish Curry + Millet Roti",
            "Target: ~2000 kcal",
        ],
    },
    "MG": {
        "name": "Muscle Gain (MG)",
        "factor": 35,
        "focus": "Hypertrophy",
        "workout": [
            "Mon: Squat 5x5",
            "Tue: Bench 5x5",
            "Wed: Deadlift 4x6",
            "Thu: Front Squat 4x8",
            "Fri: Incline Press 4x10",
            "Sat: Barbell Rows 4x10",
        ],
        "diet": [
            "Breakfast: Eggs + Peanut Butter Oats",
            "Lunch: Chicken Biryani",
            "Dinner: Mutton Curry + Rice",
            "Target: ~3200 kcal",
        ],
    },
    "BG": {
        "name": "Beginner (BG)",
        "factor": 26,
        "focus": "Full Body",
        "workout": [
            "Full Body Circuit: Air Squats, Ring Rows, Push-ups",
            "Focus: Technique & Consistency",
        ],
        "diet": [
            "Balanced Tamil Meals: Idli / Dosa / Rice + Dal",
            "Protein Target: 120g/day",
        ],
    },
}

EXERCISE_POOL = {
    "Hypertrophy": ["Leg Press", "Incline Dumbbell Press", "Lat Pulldown",
                    "Lateral Raise", "Bicep Curl", "Tricep Extension"],
    "Conditioning": ["Running", "Cycling", "Rowing", "Burpees", "Jump Rope",
                     "Kettlebell Swings"],
    "Full Body": ["Push-Up", "Pull-Up", "Lunge", "Plank", "Dumbbell Row",
                  "Dumbbell Press"],
}

# level -> (sets range, reps range, training days per week)
LEVELS = {
    "beginner": ((2, 3), (8, 12), 3),
    "intermediate": ((3, 4), (8, 15), 4),
    "advanced": ((4, 5), (6, 15), 5),
}

WORKOUT_TYPES = ["Strength", "Hypertrophy", "Cardio", "Mobility"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    age INTEGER,
    height REAL,
    weight REAL,
    program TEXT,
    calories INTEGER,
    target_weight REAL,
    target_adherence INTEGER,
    membership_expiry TEXT
);
CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL,
    week TEXT,
    adherence INTEGER
);
CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL,
    date TEXT,
    workout_type TEXT,
    duration_min INTEGER,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL,
    date TEXT,
    weight REAL,
    waist REAL,
    bodyfat REAL
);
"""


class ValidationError(ValueError):
    """Raised when client input is invalid; returned to the caller as HTTP 400."""


# ---------- Business logic (framework independent) ----------

def calculate_calories(weight, program_code):
    """Daily calorie estimate: body weight (kg) x programme factor."""
    if program_code not in PROGRAMS:
        raise ValidationError(f"Unknown program '{program_code}'")
    if weight is None or weight <= 0:
        raise ValidationError("weight must be greater than 0")
    return int(weight * PROGRAMS[program_code]["factor"])


def calculate_bmi(weight, height_cm):
    """Return BMI (1 decimal), its category and a short risk note."""
    if weight is None or height_cm is None or weight <= 0 or height_cm <= 0:
        raise ValidationError("weight and height must be greater than 0")
    bmi = round(weight / (height_cm / 100.0) ** 2, 1)
    if bmi < 18.5:
        category, risk = "Underweight", "Potential nutrient deficiency, low energy."
    elif bmi < 25:
        category, risk = "Normal", "Low risk if active and strong."
    elif bmi < 30:
        category, risk = ("Overweight",
                          "Moderate risk; focus on adherence and progressive activity.")
    else:
        category, risk = ("Obese",
                          "Higher risk; prioritize fat loss, consistency, and supervision.")
    return {"bmi": bmi, "category": category, "risk": risk}


def membership_status(expiry, today=None):
    """Return 'Active', 'Expired' or 'Unknown' for an ISO expiry date."""
    if not expiry:
        return "Unknown"
    today = today or date.today()
    return "Active" if parse_date(expiry) >= today else "Expired"


def generate_program(program_code, level, rng=None):
    """Build a weekly plan of exercises for a programme and experience level."""
    level = (level or "").lower()
    if level not in LEVELS:
        raise ValidationError("level must be beginner, intermediate or advanced")
    if program_code not in PROGRAMS:
        raise ValidationError(f"Unknown program '{program_code}'")
    rng = rng or random
    sets_range, reps_range, days = LEVELS[level]
    pool = EXERCISE_POOL[PROGRAMS[program_code]["focus"]]
    week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][:days]
    per_day = 3 if days < 4 else 4
    return [
        {"day": day, "exercise": exercise,
         "sets": rng.randint(*sets_range), "reps": rng.randint(*reps_range)}
        for day in week
        for exercise in rng.sample(pool, k=per_day)
    ]


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValidationError("dates must use the format YYYY-MM-DD") from None


def to_number(value, field, cast=float, minimum=0, maximum=None, required=False):
    """Convert a request value to a number, enforcing an allowed range."""
    if value is None or value == "":
        if required:
            raise ValidationError(f"{field} is required")
        return None
    try:
        number = cast(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number") from None
    if number < minimum or (maximum is not None and number > maximum):
        raise ValidationError(f"{field} is out of range")
    return number


# ---------- Database helpers ----------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def init_db(app):
    with sqlite3.connect(app.config["DATABASE"]) as conn:
        conn.executescript(SCHEMA)


def require_client(name):
    row = get_db().execute("SELECT * FROM clients WHERE name=?", (name,)).fetchone()
    if row is None:
        raise LookupError(f"Client '{name}' not found")
    return row


def rows(query, args=()):
    return [dict(r) for r in get_db().execute(query, args).fetchall()]


# ---------- Application factory ----------

def create_app(config=None):
    app = Flask(__name__)
    app.config["DATABASE"] = os.environ.get("ACEEST_DB", "aceest_fitness.db")
    app.config.update(config or {})
    init_db(app)

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.errorhandler(ValidationError)
    def bad_request(err):
        return jsonify(error=str(err)), 400

    @app.errorhandler(LookupError)
    def not_found(err):
        return jsonify(error=str(err.args[0])), 404

    @app.errorhandler(404)
    def no_route(_err):
        return jsonify(error="Resource not found"), 404

    @app.get("/")
    def index():
        return jsonify(service="ACEest Fitness & Gym", version=APP_VERSION,
                       endpoints=sorted(str(r) for r in app.url_map.iter_rules()
                                        if r.endpoint != "static"))

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    # ----- Programmes and calculators -----
    @app.get("/programs")
    def list_programs():
        return jsonify(PROGRAMS)

    @app.get("/programs/<code>")
    def get_program(code):
        if code.upper() not in PROGRAMS:
            raise LookupError(f"Program '{code}' not found")
        return jsonify(PROGRAMS[code.upper()])

    @app.get("/calories")
    def calories():
        weight = to_number(request.args.get("weight"), "weight", required=True)
        program = request.args.get("program", "").upper()
        return jsonify(weight=weight, program=program,
                       calories=calculate_calories(weight, program))

    @app.get("/bmi")
    def bmi():
        weight = to_number(request.args.get("weight"), "weight", required=True)
        height = to_number(request.args.get("height"), "height", required=True)
        return jsonify(calculate_bmi(weight, height))

    # ----- Clients -----
    @app.post("/clients")
    def save_client():
        data = request.get_json(silent=True) or {}
        name = str(data.get("name") or "").strip()
        program = str(data.get("program") or "").upper()
        if not name or not program:
            raise ValidationError("name and program are required")
        weight = to_number(data.get("weight"), "weight")
        expiry = data.get("membership_expiry")
        if expiry:
            parse_date(expiry)
        cals = calculate_calories(weight, program) if weight else None
        if program not in PROGRAMS:
            raise ValidationError(f"Unknown program '{program}'")
        db = get_db()
        existed = db.execute("SELECT 1 FROM clients WHERE name=?", (name,)).fetchone()
        db.execute(
            """INSERT INTO clients (name, age, height, weight, program, calories,
                                    target_weight, target_adherence, membership_expiry)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET
                   age=excluded.age, height=excluded.height, weight=excluded.weight,
                   program=excluded.program, calories=excluded.calories,
                   target_weight=excluded.target_weight,
                   target_adherence=excluded.target_adherence,
                   membership_expiry=excluded.membership_expiry""",
            (name, to_number(data.get("age"), "age", int, 0, 120),
             to_number(data.get("height"), "height"), weight, program, cals,
             to_number(data.get("target_weight"), "target_weight"),
             to_number(data.get("target_adherence"), "target_adherence", int, 0, 100),
             expiry or None),
        )
        db.commit()
        return jsonify(dict(require_client(name))), 200 if existed else 201

    @app.get("/clients")
    def list_clients():
        return jsonify(rows("SELECT * FROM clients ORDER BY name"))

    @app.get("/clients/<name>")
    def get_client(name):
        return jsonify(dict(require_client(name)))

    @app.delete("/clients/<name>")
    def delete_client(name):
        require_client(name)
        db = get_db()
        db.execute("DELETE FROM clients WHERE name=?", (name,))
        for table in ("progress", "workouts", "metrics"):
            db.execute(f"DELETE FROM {table} WHERE client_name=?", (name,))
        db.commit()
        return "", 204

    @app.get("/clients/<name>/bmi")
    def client_bmi(name):
        client = require_client(name)
        return jsonify(calculate_bmi(client["weight"], client["height"]))

    @app.get("/clients/<name>/membership")
    def client_membership(name):
        expiry = require_client(name)["membership_expiry"]
        return jsonify(client=name, membership_expiry=expiry,
                       status=membership_status(expiry))

    @app.get("/clients/<name>/program-plan")
    def client_plan(name):
        client = require_client(name)
        level = request.args.get("level", "beginner")
        return jsonify(client=name, program=client["program"], level=level.lower(),
                       plan=generate_program(client["program"], level))

    # ----- Progress, workouts and body metrics -----
    @app.route("/clients/<name>/progress", methods=["GET", "POST"])
    def progress(name):
        require_client(name)
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            adherence = to_number(data.get("adherence"), "adherence", int, 0, 100,
                                  required=True)
            week = data.get("week") or datetime.now().strftime("Week %U - %Y")
            db = get_db()
            db.execute("INSERT INTO progress (client_name, week, adherence) "
                       "VALUES (?,?,?)", (name, week, adherence))
            db.commit()
            return jsonify(client=name, week=week, adherence=adherence), 201
        return jsonify(rows("SELECT week, adherence FROM progress "
                            "WHERE client_name=? ORDER BY id", (name,)))

    @app.route("/clients/<name>/workouts", methods=["GET", "POST"])
    def workouts(name):
        require_client(name)
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            workout_type = data.get("workout_type")
            if workout_type not in WORKOUT_TYPES:
                raise ValidationError(f"workout_type must be one of {WORKOUT_TYPES}")
            day = data.get("date") or date.today().isoformat()
            parse_date(day)
            duration = to_number(data.get("duration_min", 60), "duration_min", int, 1)
            db = get_db()
            cur = db.execute(
                "INSERT INTO workouts (client_name, date, workout_type, duration_min,"
                " notes) VALUES (?,?,?,?,?)",
                (name, day, workout_type, duration, data.get("notes", "")))
            db.commit()
            return jsonify(id=cur.lastrowid, client=name, date=day,
                           workout_type=workout_type, duration_min=duration), 201
        return jsonify(rows("SELECT id, date, workout_type, duration_min, notes "
                            "FROM workouts WHERE client_name=? ORDER BY date DESC, "
                            "id DESC", (name,)))

    @app.route("/clients/<name>/metrics", methods=["GET", "POST"])
    def metrics(name):
        require_client(name)
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            day = data.get("date") or date.today().isoformat()
            parse_date(day)
            weight = to_number(data.get("weight"), "weight", required=True)
            waist = to_number(data.get("waist"), "waist")
            bodyfat = to_number(data.get("bodyfat"), "bodyfat", maximum=100)
            db = get_db()
            db.execute("INSERT INTO metrics (client_name, date, weight, waist, bodyfat)"
                       " VALUES (?,?,?,?,?)", (name, day, weight, waist, bodyfat))
            db.commit()
            return jsonify(client=name, date=day, weight=weight, waist=waist,
                           bodyfat=bodyfat), 201
        return jsonify(rows("SELECT date, weight, waist, bodyfat FROM metrics "
                            "WHERE client_name=? ORDER BY date, id", (name,)))

    # ----- Export -----
    @app.get("/export/clients.csv")
    def export_csv():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Name", "Age", "Height", "Weight", "Program", "Calories",
                         "Membership Expiry"])
        for c in rows("SELECT * FROM clients ORDER BY name"):
            writer.writerow([c["name"], c["age"], c["height"], c["weight"],
                             c["program"], c["calories"], c["membership_expiry"]])
        return Response(buffer.getvalue(), mimetype="text/csv", headers={
            "Content-Disposition": "attachment; filename=clients.csv"})

    return app


if __name__ == "__main__":  # pragma: no cover
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
