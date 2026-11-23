"""Tests for the Kubernetes deploy tool (k8s/deployctl.py) against a fake cluster."""
import io
import json
import re
import subprocess

import pytest

import deployctl
from deployctl import STRATEGIES, DeployError, Deployer, Kubectl

SERVICE_TO_DEPLOYMENT = {"aceest-rolling": "aceest-rolling", "aceest-canary": "aceest-canary",
                         "aceest-b": "aceest-b", "aceest-shadow": "aceest-shadow"}


def image(build, version="2.0.0"):
    return f"me/aceest-fitness:{version}-b{build}"


class FakeCluster:
    """Just enough of kubectl's behaviour to exercise every strategy."""

    def __init__(self):
        self.history = {}          # deployment -> list of images (last one is live)
        self.live = None           # blue-green service selector
        self.previous = None       # blue-green previous-track annotation
        self.weight = None         # canary ingress weight
        self.crash = set()         # images whose rollout never becomes ready
        self.bad = set()           # images that report the wrong version
        self.service_broken = False
        self.calls = []

    def image(self, deployment):
        return self.history[deployment][-1]

    def install(self, strategy, img):
        spec = STRATEGIES[strategy]
        for deployment in (spec["baseline"], spec["target"]):
            self.history[deployment] = [img]
        if strategy == "blue-green":
            self.live, self.previous = "blue", "green"
        if strategy == "canary":
            self.weight = "0"

    def answer(self, deployment):
        img = self.image(deployment)
        tag = img.rsplit(":", 1)[1]
        version, build = tag.split("-b")
        if img in self.bad:
            version = "0.0.0-broken"
        return json.dumps({"service": "ACEest Fitness & Gym", "version": version,
                           "build": build, "track": Deployer.track_of(deployment)})

    def __call__(self, *args, stdin=None, check=True):
        self.calls.append(args)
        a = list(args)
        if a[:2] == ["apply", "-f"]:
            img = re.search(r"image: (\S+)", stdin).group(1)
            names = set(re.findall(r"name: (aceest-[a-z-]+)", stdin))
            strategy = next(s for s, spec in STRATEGIES.items() if spec["baseline"] in names)
            self.install(strategy, img)
            return ""
        if a[:2] == ["get", "deployment"] and "--ignore-not-found" in a:
            return f"deployment.apps/{a[2]}" if a[2] in self.history else ""
        if a[:2] == ["get", "deployment"]:
            return self.image(a[2])
        if a[:2] == ["set", "image"]:
            deployment = a[2].split("/")[1]
            self.history[deployment].append(a[3].split("=", 1)[1])
            return ""
        if a[:2] == ["rollout", "status"]:
            deployment = a[2].split("/")[1]
            if self.image(deployment) in self.crash:
                raise DeployError(f"deployment {deployment} exceeded its progress deadline")
            return "successfully rolled out"
        if a[:2] == ["rollout", "undo"]:
            self.history[a[2].split("/")[1]].pop()
            return ""
        if a[:3] == ["get", "service", "aceest-bluegreen"]:
            return self.previous if "previous-track" in a[-1] else (self.live or "")
        if a[:2] == ["patch", "service"]:
            patch = json.loads(a[-1])
            self.live = patch["spec"]["selector"]["track"]
            self.previous = patch["metadata"]["annotations"][deployctl.PREVIOUS_TRACK]
            return ""
        if a[:2] == ["annotate", "ingress"]:
            self.weight = a[3].split("=")[1]
            return ""
        if a[0] == "exec":
            url = a[-1]
            if url == "http://localhost:5000":
                return self.answer(a[1].split("/")[1])
            if self.service_broken:
                raise DeployError("connection refused")
            if url == "http://aceest-bluegreen":
                return self.answer(f"aceest-{self.live}")
            return self.answer(SERVICE_TO_DEPLOYMENT[url.split("//")[1]])
        if a[:2] == ["get", "deployments"]:
            return "\n".join(f"{d} {imgs[-1]}" for d, imgs in self.history.items())
        if a[:2] == ["get", "ingress"]:
            return self.weight or ""
        raise AssertionError(f"unexpected kubectl call: {args}")


@pytest.fixture
def cluster():
    return FakeCluster()


@pytest.fixture
def deployer(cluster):
    return Deployer(cluster, sleep=lambda _s: None)


def installed(cluster, deployer, strategy, build=1):
    deployer.deploy(strategy, image(build), "2.0.0", str(build))
    return cluster


# ---------- manifests ----------

@pytest.mark.parametrize("strategy", list(STRATEGIES))
def test_render_fills_in_the_image(deployer, strategy):
    text = deployer.render(strategy, "me/aceest-fitness:9.9.9")
    assert "__IMAGE__" not in text
    assert "kind: Namespace" in text
    assert "image: me/aceest-fitness:9.9.9" in text
    assert f"host: {STRATEGIES[strategy]['host']}" in text
    for name in {STRATEGIES[strategy]["baseline"], STRATEGIES[strategy]["target"]}:
        assert f"name: {name}\n" in text


@pytest.mark.parametrize("strategy", list(STRATEGIES))
def test_first_deploy_installs_and_smoke_tests(cluster, deployer, strategy):
    installed(cluster, deployer, strategy)
    assert any(call[:2] == ("apply", "-f") for call in cluster.calls)
    assert cluster.image(STRATEGIES[strategy]["target"]) == image(1)


def test_first_deploy_failure_has_nothing_to_roll_back(cluster, deployer):
    cluster.bad.add(image(1))
    with pytest.raises(DeployError, match="first install"):
        deployer.deploy("rolling", image(1), "2.0.0", "1")


# ---------- rolling update ----------

def test_rolling_update(cluster, deployer):
    installed(cluster, deployer, "rolling")
    deployer.deploy("rolling", image(2), "2.0.0", "2")
    assert cluster.image("aceest-rolling") == image(2)


@pytest.mark.parametrize("failure", ["bad", "crash"])
def test_rolling_update_rolls_back(cluster, deployer, failure):
    installed(cluster, deployer, "rolling")
    getattr(cluster, failure).add(image(2))
    with pytest.raises(DeployError):
        deployer.deploy("rolling", image(2), "2.0.0", "2")
    assert cluster.image("aceest-rolling") == image(1)
    assert ("rollout", "undo", "deployment/aceest-rolling") in cluster.calls


def test_rolling_same_image_is_not_undone(cluster, deployer):
    installed(cluster, deployer, "rolling")
    deployer.deploy("rolling", image(1), "2.0.0", "1")
    assert not any(call[:2] == ("set", "image") for call in cluster.calls)
    with pytest.raises(DeployError):
        deployer.deploy("rolling", image(1), "9.9.9")
    assert cluster.history["aceest-rolling"] == [image(1)]


# ---------- blue-green ----------

def test_blue_green_switches_and_rolls_back(cluster, deployer):
    installed(cluster, deployer, "blue-green")
    assert cluster.live == "blue"
    deployer.deploy("blue-green", image(2), "2.0.0", "2")
    assert (cluster.live, cluster.previous) == ("green", "blue")
    assert cluster.image("aceest-green") == image(2)
    deployer.deploy("blue-green", image(3), "2.0.0", "3")
    assert (cluster.live, cluster.image("aceest-blue")) == ("blue", image(3))
    deployer.rollback("blue-green")
    assert cluster.live == "green"


def test_blue_green_failure_before_cutover_keeps_live(cluster, deployer):
    installed(cluster, deployer, "blue-green")
    cluster.bad.add(image(2))
    with pytest.raises(DeployError):
        deployer.deploy("blue-green", image(2), "2.0.0", "2")
    assert cluster.live == "blue"
    assert cluster.image("aceest-green") == image(1)
    assert not any(call[:2] == ("patch", "service") for call in cluster.calls)


def test_blue_green_failure_after_cutover_switches_back(cluster, deployer):
    installed(cluster, deployer, "blue-green")
    cluster.service_broken = True
    with pytest.raises(DeployError):
        deployer.deploy("blue-green", image(2), "2.0.0", "2")
    assert (cluster.live, cluster.previous) == ("blue", "green")


def test_blue_green_rollback_without_annotation(cluster, deployer):
    installed(cluster, deployer, "blue-green")
    cluster.previous = ""
    deployer.rollback("blue-green")
    assert cluster.live == "green"


# ---------- canary, A/B testing, shadow ----------

def test_canary_release_and_promotion(cluster, deployer):
    installed(cluster, deployer, "canary")
    assert cluster.weight == "0"
    deployer.deploy("canary", image(2), "2.0.0", "2")
    assert cluster.weight == str(deployctl.CANARY_WEIGHT)
    assert (cluster.image("aceest-stable"), cluster.image("aceest-canary")) == (image(1),
                                                                                image(2))
    deployer.promote("canary")
    assert cluster.image("aceest-stable") == image(2)
    assert cluster.weight == "0"


def test_canary_failure_rolls_back(cluster, deployer):
    installed(cluster, deployer, "canary")
    cluster.crash.add(image(2))
    with pytest.raises(DeployError):
        deployer.deploy("canary", image(2), "2.0.0", "2")
    assert cluster.weight == "0"
    assert cluster.image("aceest-canary") == image(1)


@pytest.mark.parametrize("strategy", ["ab-testing", "shadow"])
def test_paired_strategies(cluster, deployer, strategy):
    spec = STRATEGIES[strategy]
    installed(cluster, deployer, strategy)
    deployer.deploy(strategy, image(2), "2.0.0", "2")
    assert (cluster.image(spec["baseline"]), cluster.image(spec["target"])) == (image(1),
                                                                                image(2))
    cluster.bad.add(image(3))
    with pytest.raises(DeployError):
        deployer.deploy(strategy, image(3), "2.0.0", "3")
    assert cluster.image(spec["target"]) == image(1)
    deployer.deploy(strategy, image(4), "2.0.0", "4")
    deployer.promote(strategy)
    assert cluster.image(spec["baseline"]) == image(4)


@pytest.mark.parametrize("strategy", ["rolling", "blue-green"])
def test_promote_is_a_no_op_when_already_live(cluster, deployer, strategy):
    installed(cluster, deployer, strategy)
    before = len(cluster.calls)
    deployer.promote(strategy)
    assert len(cluster.calls) == before


# ---------- smoke test details ----------

def test_probe_retries_then_succeeds(cluster):
    sleeps = []
    deployer = Deployer(cluster, sleep=sleeps.append)
    installed(cluster, deployer, "rolling")
    real_call = cluster.__call__
    failures = iter([DeployError("pod not ready"), "not json"])

    def flaky(*args, **kwargs):
        if args[0] == "exec":
            outcome = next(failures, None)
            if isinstance(outcome, Exception):
                raise outcome
            if outcome is not None:
                return outcome
        return real_call(*args, **kwargs)

    deployer.k = flaky
    info = deployer.probe("aceest-rolling", "http://localhost:5000", "rolling", "2.0.0", "1")
    assert info["build"] == "1"
    assert sleeps == [3, 3]


def test_probe_gives_up(cluster, deployer):
    installed(cluster, deployer, "rolling")
    with pytest.raises(DeployError, match="smoke test failed"):
        deployer.probe("aceest-rolling", "http://localhost:5000", "rolling", "7.7.7")


# ---------- kubectl wrapper ----------

def test_kubectl_wrapper(capsys):
    seen = []

    def runner(cmd, **kwargs):
        seen.append((cmd, kwargs["input"]))
        code = 1 if "fail" in cmd else 0
        return subprocess.CompletedProcess(cmd, code, stdout=" out \n", stderr="boom")

    kubectl = Kubectl(runner=runner)
    assert kubectl("get", "pods", stdin="x") == "out"
    assert seen[0] == (["kubectl", "-n", "aceest", "get", "pods"], "x")
    with pytest.raises(DeployError, match="boom"):
        kubectl("fail")
    assert kubectl("fail", check=False) == "out"
    assert "+ kubectl -n aceest get pods" in capsys.readouterr().out


# ---------- command line ----------

def test_main_deploy_all_and_failures(cluster, deployer):
    assert deployctl.main(["deploy", "all", "--image", image(1), "--expect-version",
                           "2.0.0", "--expect-build", "1"], deployer) == 0
    cluster.bad.add(image(2))
    assert deployctl.main(["deploy", "canary", "--image", image(2)], deployer) == 0
    assert deployctl.main(["deploy", "shadow", "--image", image(2),
                           "--expect-version", "2.0.0"], deployer) == 1
    assert deployctl.main(["smoke", "all"], deployer) == 0
    assert deployctl.main(["deploy", "rolling", "--image", image(3)], deployer) == 0
    assert deployctl.main(["rollback", "rolling"], deployer) == 0
    assert cluster.image("aceest-rolling") == image(1)
    assert deployctl.main(["promote", "canary"], deployer) == 0
    assert deployctl.main(["status"], deployer) == 0
    cluster.crash.add(image(1))
    assert deployctl.main(["promote", "ab-testing"], deployer) == 1


def test_status_before_anything_is_installed(cluster, deployer, capsys):
    deployer.status()
    out = capsys.readouterr().out
    assert "blue-green live colour: -" in out and "canary weight (%): -" in out


def test_main_requires_an_image():
    with pytest.raises(SystemExit):
        deployctl.parse_args(["deploy", "rolling"])


def test_main_builds_a_real_deployer(monkeypatch):
    created = {}

    class Recorder(Deployer):
        def __init__(self, kubectl, **kwargs):
            created.update(kwargs, kubectl=kubectl)

        def status(self):
            created["status"] = True

    monkeypatch.setattr(deployctl, "Deployer", Recorder)
    assert deployctl.main(["--timeout", "60s", "status"]) == 0
    assert created["timeout"] == "60s" and created["status"]
    assert isinstance(created["kubectl"], Kubectl)


def test_traffic_tally(monkeypatch, capsys):
    answers = iter([{"version": "2.0.0", "build": "1", "track": "stable"}] * 3
                   + [{"version": "2.0.0", "build": "2", "track": "canary"}])
    sent = []

    def opener(request, timeout):
        sent.append(dict(request.header_items()))
        return io.BytesIO(json.dumps(next(answers)).encode())

    tally = deployctl.traffic("canary.aceest.local", "10.0.0.1", 4, "X-Variant: B", opener)
    assert tally["2.0.0 build 1 (stable)"] == 3
    assert sent[0]["Host"] == "canary.aceest.local" and sent[0]["X-variant"] == "B"

    monkeypatch.setattr(deployctl, "traffic", lambda *a: sent.append(a))
    assert deployctl.main(["traffic", "ab-testing", "--ip", "1.2.3.4", "--count", "2"]) == 0
    assert sent[-1] == ("ab.aceest.local", "1.2.3.4", 2, None)
    assert "3  2.0.0 build 1 (stable)" in capsys.readouterr().out
