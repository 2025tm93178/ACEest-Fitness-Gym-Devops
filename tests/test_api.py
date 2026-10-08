"""Tests for the HTTP endpoints, each run against a fresh database."""


def test_index_and_health(client):
    assert client.get("/health").get_json() == {"status": "ok"}
    body = client.get("/").get_json()
    assert body["service"] == "ACEest Fitness & Gym"
    assert "/clients" in body["endpoints"]


def test_programs(client):
    assert set(client.get("/programs").get_json()) == {"FL", "MG", "BG"}
    assert client.get("/programs/fl").get_json()["factor"] == 22
    assert client.get("/programs/XX").status_code == 404


def test_calories_endpoint(client):
    resp = client.get("/calories?weight=70&program=MG")
    assert resp.get_json()["calories"] == 2450
    assert client.get("/calories?program=MG").status_code == 400
    assert client.get("/calories?weight=abc&program=MG").status_code == 400


def test_bmi_endpoint(client):
    assert client.get("/bmi?weight=70&height=175").get_json()["category"] == "Normal"
    assert client.get("/bmi?weight=70").status_code == 400


def test_create_and_get_client(client, ravi):
    body = client.get("/clients/Ravi").get_json()
    assert body["calories"] == 2450
    assert body["program"] == "MG"
    assert [c["name"] for c in client.get("/clients").get_json()] == ["Ravi"]


def test_saving_existing_client_updates_it(client, ravi):
    resp = client.post("/clients", json={**ravi, "weight": 80, "program": "FL"})
    assert resp.status_code == 200
    assert resp.get_json()["calories"] == 1760
    assert len(client.get("/clients").get_json()) == 1


def test_client_validation(client):
    assert client.post("/clients", json={"name": "NoProgram"}).status_code == 400
    assert client.post("/clients", json={"program": "MG"}).status_code == 400
    bad_program = {"name": "A", "program": "ZZ", "weight": 70}
    assert client.post("/clients", json=bad_program).status_code == 400
    assert client.post("/clients", json={"name": "A", "program": "ZZ"}).status_code == 400
    bad_date = {"name": "A", "program": "MG", "membership_expiry": "31-12-2026"}
    assert client.post("/clients", json=bad_date).status_code == 400
    assert client.get("/clients").get_json() == []


def test_unknown_client_returns_404(client):
    for path in ("/clients/Ghost", "/clients/Ghost/progress",
                 "/clients/Ghost/workouts", "/clients/Ghost/membership"):
        assert client.get(path).status_code == 404


def test_delete_client_removes_history(client, ravi):
    client.post("/clients/Ravi/progress", json={"adherence": 80})
    assert client.delete("/clients/Ravi").status_code == 204
    assert client.get("/clients/Ravi").status_code == 404
    client.post("/clients", json=ravi)
    assert client.get("/clients/Ravi/progress").get_json() == []


def test_progress_logging(client, ravi):
    resp = client.post("/clients/Ravi/progress",
                       json={"adherence": 85, "week": "Week 01 - 2026"})
    assert resp.status_code == 201
    client.post("/clients/Ravi/progress", json={"adherence": 90})
    history = client.get("/clients/Ravi/progress").get_json()
    assert [p["adherence"] for p in history] == [85, 90]
    assert history[0]["week"] == "Week 01 - 2026"


def test_progress_rejects_out_of_range(client, ravi):
    for bad in ({"adherence": 150}, {"adherence": -1}, {}):
        assert client.post("/clients/Ravi/progress", json=bad).status_code == 400


def test_workout_logging(client, ravi):
    ok = {"date": "2026-01-10", "workout_type": "Strength", "duration_min": 45}
    assert client.post("/clients/Ravi/workouts", json=ok).status_code == 201
    client.post("/clients/Ravi/workouts",
                json={"date": "2026-01-12", "workout_type": "Cardio"})
    history = client.get("/clients/Ravi/workouts").get_json()
    assert [w["date"] for w in history] == ["2026-01-12", "2026-01-10"]
    assert history[0]["duration_min"] == 60
    bad = {"workout_type": "Yoga"}
    assert client.post("/clients/Ravi/workouts", json=bad).status_code == 400


def test_metrics_logging(client, ravi):
    ok = {"date": "2026-01-10", "weight": 69.5, "waist": 82, "bodyfat": 18}
    assert client.post("/clients/Ravi/metrics", json=ok).status_code == 201
    assert client.get("/clients/Ravi/metrics").get_json()[0]["weight"] == 69.5
    assert client.post("/clients/Ravi/metrics", json={"waist": 80}).status_code == 400


def test_client_bmi_membership_and_plan(client, ravi):
    assert client.get("/clients/Ravi/bmi").get_json()["bmi"] == 22.9
    assert client.get("/clients/Ravi/membership").get_json()["status"] == "Active"
    plan = client.get("/clients/Ravi/program-plan?level=advanced").get_json()
    assert len(plan["plan"]) == 20
    assert client.get("/clients/Ravi/program-plan?level=x").status_code == 400


def test_csv_export(client, ravi):
    resp = client.get("/export/clients.csv")
    assert resp.mimetype == "text/csv"
    lines = resp.get_data(as_text=True).strip().splitlines()
    assert lines[0].startswith("Name,Age")
    assert lines[1].startswith("Ravi,30")


def test_unknown_route_returns_json_404(client):
    resp = client.get("/no-such-page")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Resource not found"}


def test_client_rejects_non_json_body(client):
    resp = client.post("/clients", data="name=A", content_type="text/plain")
    assert resp.status_code == 400


def test_client_field_ranges(client):
    base = {"name": "A", "program": "MG"}
    for bad in ({"age": 150}, {"age": "old"}, {"target_adherence": 101},
                {"height": -1}):
        assert client.post("/clients", json={**base, **bad}).status_code == 400


def test_client_without_measurements(client):
    resp = client.post("/clients", json={"name": "Asha", "program": "bg"})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["program"] == "BG" and body["calories"] is None
    assert client.get("/clients/Asha/bmi").status_code == 400
    assert client.get("/clients/Asha/membership").get_json()["status"] == "Unknown"


def test_expired_membership(client):
    client.post("/clients", json={"name": "Old", "program": "FL",
                                  "membership_expiry": "2020-01-01"})
    body = client.get("/clients/Old/membership").get_json()
    assert body == {"client": "Old", "membership_expiry": "2020-01-01",
                    "status": "Expired"}


def test_delete_unknown_client_returns_404(client):
    assert client.delete("/clients/Ghost").status_code == 404


def test_workout_rejects_bad_date_and_duration(client, ravi):
    url = "/clients/Ravi/workouts"
    assert client.post(url, json={"workout_type": "Cardio", "date": "banana"}).status_code == 400
    assert client.post(url, json={"workout_type": "Cardio", "duration_min": 0}).status_code == 400
    assert client.get(url).get_json() == []


def test_metrics_rejects_bad_values(client, ravi):
    url = "/clients/Ravi/metrics"
    for bad in ({"weight": 70, "bodyfat": 150}, {"weight": -1},
                {"weight": 70, "date": "2026-13-01"}):
        assert client.post(url, json=bad).status_code == 400
    assert client.get(url).get_json() == []


def test_program_plan_defaults_to_beginner(client, ravi):
    body = client.get("/clients/Ravi/program-plan").get_json()
    assert body["level"] == "beginner"
    assert len(body["plan"]) == 9


def test_csv_export_with_no_clients(client):
    resp = client.get("/export/clients.csv")
    assert resp.headers["Content-Disposition"] == "attachment; filename=clients.csv"
    assert resp.get_data(as_text=True).strip().splitlines() == [
        "Name,Age,Height,Weight,Program,Calories,Membership Expiry"]


def test_wsgi_entry_point(tmp_path, monkeypatch):
    import importlib
    import sys

    monkeypatch.setenv("ACEEST_DB", str(tmp_path / "wsgi.db"))
    sys.modules.pop("wsgi", None)
    wsgi = importlib.import_module("wsgi")
    assert wsgi.app.config["DATABASE"] == str(tmp_path / "wsgi.db")
    assert wsgi.app.test_client().get("/health").status_code == 200


def test_calories_rejects_non_finite_weight(client):
    for bad in ("inf", "nan"):
        resp = client.get(f"/calories?weight={bad}&program=MG")
        assert resp.status_code == 400
