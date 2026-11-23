"""ACEest Fitness & Gym - application entry point.

Gunicorn serves this module in the container (``gunicorn ACEest_Fitness:app``), and
``python ACEest_Fitness.py`` starts the development server. The routes and business
logic live in ``app.py``; the original desktop versions are kept in ``legacy/``.
"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":  # pragma: no cover
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
