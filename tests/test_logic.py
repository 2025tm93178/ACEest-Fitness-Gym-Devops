"""Unit tests for the framework-independent business logic."""
import random
from datetime import date

import pytest

from app import (PROGRAMS, ValidationError, calculate_bmi, calculate_calories,
                 generate_program, membership_status, parse_date, to_number)


@pytest.mark.parametrize("weight, program, expected", [
    (70, "FL", 1540),
    (70, "MG", 2450),
    (70, "BG", 1820),
    (82.5, "MG", 2887),
])
def test_calculate_calories(weight, program, expected):
    assert calculate_calories(weight, program) == expected


@pytest.mark.parametrize("weight, program", [(0, "FL"), (-5, "FL"), (70, "XX")])
def test_calculate_calories_rejects_bad_input(weight, program):
    with pytest.raises(ValidationError):
        calculate_calories(weight, program)


@pytest.mark.parametrize("weight, height, category", [
    (50, 180, "Underweight"),
    (70, 175, "Normal"),
    (85, 175, "Overweight"),
    (110, 175, "Obese"),
])
def test_calculate_bmi_categories(weight, height, category):
    assert calculate_bmi(weight, height)["category"] == category


def test_calculate_bmi_value():
    assert calculate_bmi(70, 175)["bmi"] == 22.9


def test_calculate_bmi_rejects_zero_height():
    with pytest.raises(ValidationError):
        calculate_bmi(70, 0)


def test_membership_status():
    today = date(2026, 1, 15)
    assert membership_status("2026-01-15", today) == "Active"
    assert membership_status("2026-01-14", today) == "Expired"
    assert membership_status(None, today) == "Unknown"


@pytest.mark.parametrize("level, days, per_day", [
    ("beginner", 3, 3), ("intermediate", 4, 4), ("advanced", 5, 4)])
def test_generate_program_shape(level, days, per_day):
    plan = generate_program("MG", level, random.Random(1))
    assert len(plan) == days * per_day
    assert len({row["day"] for row in plan}) == days


def test_generate_program_respects_level_ranges():
    plan = generate_program("FL", "beginner", random.Random(7))
    assert all(2 <= row["sets"] <= 3 and 8 <= row["reps"] <= 12 for row in plan)


def test_generate_program_rejects_unknown_level():
    with pytest.raises(ValidationError):
        generate_program("MG", "expert")


def test_to_number_range_and_type():
    assert to_number("42", "age", int) == 42
    assert to_number(None, "age") is None
    for bad in ("abc", -1, 101):
        with pytest.raises(ValidationError):
            to_number(bad, "adherence", int, 0, 100)


def test_every_program_is_complete():
    for program in PROGRAMS.values():
        assert program["factor"] > 0 and program["workout"] and program["diet"]


def test_generate_program_rejects_unknown_program():
    with pytest.raises(ValidationError):
        generate_program("XX", "beginner")


def test_membership_status_defaults_to_today():
    assert membership_status("2999-12-31") == "Active"
    assert membership_status("2000-01-01") == "Expired"


def test_parse_date():
    assert parse_date("2026-02-28") == date(2026, 2, 28)
    for bad in ("2026-02-30", "28-02-2026", None):
        with pytest.raises(ValidationError):
            parse_date(bad)


def test_to_number_required_and_maximum():
    with pytest.raises(ValidationError):
        to_number("", "weight", required=True)
    assert to_number("72.5", "weight") == 72.5
    assert to_number(100, "bodyfat", maximum=100) == 100
