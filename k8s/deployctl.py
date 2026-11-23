"""Deploy ACEest Fitness & Gym to Kubernetes with a chosen strategy.

Every deployment is smoke tested inside the cluster, and a failed rollout or smoke
test is rolled back automatically to the last stable version.

Usage:
    python k8s/deployctl.py deploy <strategy|all> --image IMAGE
                                   [--expect-version V] [--expect-build B]
    python k8s/deployctl.py rollback <strategy|all>
    python k8s/deployctl.py promote  <canary|ab-testing|shadow>
    python k8s/deployctl.py smoke    <strategy|all> [--expect-version V] [--expect-build B]
    python k8s/deployctl.py status
    python k8s/deployctl.py traffic  <strategy> --ip INGRESS_IP [--count N] [--header 'K: V']

Strategies: rolling, blue-green, canary, ab-testing, shadow. The first deploy of a
strategy installs its manifests (k8s/<strategy>/*.yaml) with the given image.
Needs kubectl on the PATH, pointed at the cluster (KUBECONFIG or ~/.kube/config).
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from collections import Counter

NAMESPACE = "aceest"
MANIFEST_DIR = os.path.dirname(os.path.abspath(__file__))
CANARY_WEIGHT = 20
WEIGHT_ANNOTATION = "nginx.ingress.kubernetes.io/canary-weight"
PREVIOUS_TRACK = "aceest.io/previous-track"

# For each strategy: the deployment that serves users today (baseline), the one that
# receives the new release (target), and the service/host it is reached through.
STRATEGIES = {
    "rolling": {"baseline": "aceest-rolling", "target": "aceest-rolling",
                "service": "aceest-rolling", "host": "rolling.aceest.local"},
    "blue-green": {"baseline": "aceest-blue", "target": "aceest-green",
                   "service": "aceest-bluegreen", "host": "bluegreen.aceest.local"},
    "canary": {"baseline": "aceest-stable", "target": "aceest-canary",
               "service": "aceest-canary", "host": "canary.aceest.local"},
    "ab-testing": {"baseline": "aceest-a", "target": "aceest-b",
                   "service": "aceest-b", "host": "ab.aceest.local"},
    "shadow": {"baseline": "aceest-primary", "target": "aceest-shadow",
               "service": "aceest-shadow", "host": "shadow.aceest.local"},
}

# Run inside an application pod: check /health, then print the /version JSON.
SMOKE_SCRIPT = (
    "import sys, urllib.request as u; b = sys.argv[1]; "
    "u.urlopen(b + '/health', timeout=5).read(); "
    "print(u.urlopen(b + '/version', timeout=5).read().decode())"
)


class DeployError(RuntimeError):
    """A rollout, smoke test or kubectl command failed."""


class Kubectl:
    """Thin wrapper around the kubectl CLI, scoped to the ACEest namespace."""

    def __init__(self, namespace=NAMESPACE, runner=subprocess.run, binary="kubectl"):
        self.namespace = namespace
        self.runner = runner
        self.binary = binary

    def __call__(self, *args, stdin=None, check=True):
        cmd = [self.binary, "-n", self.namespace, *args]
        print("+ " + " ".join(cmd), flush=True)
        result = self.runner(cmd, input=stdin, capture_output=True, text=True)
        if check and result.returncode != 0:
            raise DeployError(f"kubectl {' '.join(args)} failed: "
                              f"{(result.stderr or result.stdout).strip()}")
        return (result.stdout or "").strip()


class Deployer:
    def __init__(self, kubectl, manifest_dir=MANIFEST_DIR, timeout="180s",
                 retries=5, sleep=time.sleep):
        self.k = kubectl
        self.manifest_dir = manifest_dir
        self.timeout = timeout
        self.retries = retries
        self.sleep = sleep

    # ----- kubectl helpers -----
    def exists(self, deployment):
        return bool(self.k("get", "deployment", deployment, "--ignore-not-found", "-o", "name"))

    def image_of(self, deployment):
        return self.k("get", "deployment", deployment, "-o",
                      "jsonpath={.spec.template.spec.containers[0].image}")

    def set_image(self, deployment, image):
        self.k("set", "image", f"deployment/{deployment}", f"aceest={image}")

    def wait(self, deployment):
        self.k("rollout", "status", f"deployment/{deployment}", f"--timeout={self.timeout}")

    def live_colour(self):
        return self.k("get", "service", "aceest-bluegreen", "--ignore-not-found", "-o",
                      "jsonpath={.spec.selector.track}")

    def switch_colour(self, colour, previous):
        patch = {"metadata": {"annotations": {PREVIOUS_TRACK: previous}},
                 "spec": {"selector": {"track": colour}}}
        self.k("patch", "service", "aceest-bluegreen", "-p", json.dumps(patch))

    def set_weight(self, weight):
        self.k("annotate", "ingress", "aceest-canary-weighted",
               f"{WEIGHT_ANNOTATION}={weight}", "--overwrite")

    def render(self, strategy, image):
        """The strategy's manifests (and the namespace) with the image filled in."""
        paths = [os.path.join(self.manifest_dir, "namespace.yaml")]
        folder = os.path.join(self.manifest_dir, strategy)
        paths += [os.path.join(folder, name) for name in sorted(os.listdir(folder))
                  if name.endswith(".yaml")]
        docs = []
        for path in paths:
            with open(path, encoding="utf-8") as handle:
                docs.append(handle.read().replace("__IMAGE__", image).strip())
        return "\n---\n".join(docs) + "\n"

    def install(self, strategy, image):
        print(f"== {strategy}: first deployment, installing manifests with {image}")
        self.k("apply", "-f", "-", stdin=self.render(strategy, image))
        spec = STRATEGIES[strategy]
        for deployment in dict.fromkeys((spec["baseline"], spec["target"])):
            self.wait(deployment)

    # ----- smoke tests -----
    def probe(self, deployment, url, track, expect_version=None, expect_build=None):
        """Call /health and /version from inside a pod of `deployment` and check them."""
        error = None
        for attempt in range(1, self.retries + 1):
            try:
                out = self.k("exec", f"deployment/{deployment}", "--", "python", "-c",
                             SMOKE_SCRIPT, url)
                info = json.loads(out.splitlines()[-1])
                expected = {"track": track, "version": expect_version, "build": expect_build}
                wrong = {key: info.get(key) for key, value in expected.items()
                         if value is not None and str(info.get(key)) != str(value)}
                if not wrong:
                    print(f"   smoke ok via {url}: {info}")
                    return info
                error = f"expected {expected}, got {info}"
            except (DeployError, ValueError, IndexError) as exc:
                error = str(exc)
            print(f"   smoke attempt {attempt}/{self.retries} failed: {error}")
            if attempt < self.retries:
                self.sleep(3)
        raise DeployError(f"smoke test failed for {deployment} ({url}): {error}")

    def smoke(self, strategy, expect_version=None, expect_build=None):
        spec = STRATEGIES[strategy]
        if strategy == "blue-green":
            live = self.live_colour()
            return self.probe(f"aceest-{live}", "http://aceest-bluegreen", live,
                              expect_version, expect_build)
        deployment = spec["target"]
        track = self.track_of(deployment)
        self.probe(deployment, "http://localhost:5000", track, expect_version, expect_build)
        return self.probe(deployment, f"http://{spec['service']}", track,
                          expect_version, expect_build)

    @staticmethod
    def track_of(deployment):
        return {"aceest-rolling": "rolling", "aceest-stable": "stable",
                "aceest-canary": "canary", "aceest-a": "variant-a", "aceest-b": "variant-b",
                "aceest-primary": "primary", "aceest-shadow": "shadow",
                "aceest-blue": "blue", "aceest-green": "green"}[deployment]

    # ----- deployment strategies -----
    def deploy(self, strategy, image, expect_version=None, expect_build=None):
        spec = STRATEGIES[strategy]
        if not self.exists(spec["baseline"]):
            self.install(strategy, image)
            try:
                self.smoke(strategy, expect_version, expect_build)
            except DeployError as exc:
                raise DeployError(f"{exc} (first install: no earlier version to roll back to)")
            return
        handler = {"rolling": self._rolling, "blue-green": self._blue_green,
                   "canary": self._canary}.get(strategy, self._paired)
        handler(strategy, image, expect_version, expect_build)

    def _rolling(self, strategy, image, expect_version, expect_build):
        if self.image_of("aceest-rolling") == image:
            # No new revision is created, so 'rollout undo' would go back one release too far.
            print(f"== rolling: {image} is already running, re-testing it")
            self.smoke(strategy, expect_version, expect_build)
            return
        print(f"== rolling: updating aceest-rolling to {image}")
        self.set_image("aceest-rolling", image)
        try:
            self.wait("aceest-rolling")
            self.smoke(strategy, expect_version, expect_build)
        except DeployError:
            self.rollback(strategy)
            raise

    def _blue_green(self, strategy, image, expect_version, expect_build):
        live = self.live_colour()
        idle = "green" if live == "blue" else "blue"
        print(f"== blue-green: live={live}, deploying {image} to idle {idle}")
        self.set_image(f"aceest-{idle}", image)
        try:
            self.wait(f"aceest-{idle}")
            self.probe(f"aceest-{idle}", "http://localhost:5000", idle,
                       expect_version, expect_build)
        except DeployError:
            print(f"   {idle} failed before cut-over; live {live} was never touched")
            self.k("rollout", "undo", f"deployment/aceest-{idle}")
            raise
        print(f"== blue-green: switching live traffic {live} -> {idle}")
        self.switch_colour(idle, previous=live)
        try:
            self.smoke(strategy, expect_version, expect_build)
        except DeployError:
            self.rollback(strategy)
            raise

    def _canary(self, strategy, image, expect_version, expect_build):
        stable_image = self.image_of("aceest-stable")
        print(f"== canary: stable={stable_image}, canary -> {image}")
        self.set_image("aceest-canary", image)
        try:
            self.wait("aceest-canary")
            self.smoke(strategy, expect_version, expect_build)
        except DeployError:
            self.rollback(strategy)
            raise
        self.set_weight(CANARY_WEIGHT)
        print(f"   canary receives {CANARY_WEIGHT}% of traffic; "
              "run 'promote canary' to make it stable")

    def _paired(self, strategy, image, expect_version, expect_build):
        spec = STRATEGIES[strategy]
        print(f"== {strategy}: deploying {image} to {spec['target']}")
        self.set_image(spec["target"], image)
        try:
            self.wait(spec["target"])
            self.smoke(strategy, expect_version, expect_build)
        except DeployError:
            self.rollback(strategy)
            raise

    def rollback(self, strategy):
        """Return the strategy to the last stable version."""
        spec = STRATEGIES[strategy]
        print(f"== {strategy}: ROLLING BACK to the last stable version")
        if strategy == "rolling":
            self.k("rollout", "undo", "deployment/aceest-rolling")
            self.wait("aceest-rolling")
        elif strategy == "blue-green":
            current = self.live_colour()
            previous = self.k("get", "service", "aceest-bluegreen", "-o",
                              "jsonpath={.metadata.annotations.aceest\\.io/previous-track}")
            previous = previous or ("green" if current == "blue" else "blue")
            self.switch_colour(previous, previous=current)
            print(f"   live traffic switched back {current} -> {previous}")
        else:
            if strategy == "canary":
                self.set_weight(0)
            self.set_image(spec["target"], self.image_of(spec["baseline"]))
            self.wait(spec["target"])
        print(f"== {strategy}: rollback complete")

    def promote(self, strategy):
        """Make the release under test the new baseline (canary, A/B, shadow)."""
        spec = STRATEGIES[strategy]
        if strategy in ("rolling", "blue-green"):
            print(f"== {strategy}: nothing to promote, the new version is already live")
            return
        image = self.image_of(spec["target"])
        print(f"== {strategy}: promoting {image} to {spec['baseline']}")
        self.set_image(spec["baseline"], image)
        self.wait(spec["baseline"])
        if strategy == "canary":
            self.set_weight(0)

    def status(self):
        print(self.k("get", "deployments", "-l", "app=aceest", "-o",
                     "custom-columns=DEPLOYMENT:.metadata.name,"
                     "IMAGE:.spec.template.spec.containers[0].image,"
                     "READY:.status.readyReplicas,DESIRED:.spec.replicas"))
        print("blue-green live colour:", self.live_colour() or "-")
        weight = self.k("get", "ingress", "aceest-canary-weighted", "--ignore-not-found",
                        "-o", "jsonpath={.metadata.annotations.nginx\\.ingress\\.kubernetes"
                        "\\.io/canary-weight}")
        print("canary weight (%):", weight or "-")
        for name, spec in STRATEGIES.items():
            print(f"  {name:11} http://{spec['host']}/version")


def traffic(host, ip, count=20, header=None, opener=None):
    """Send `count` requests through the ingress and tally which release answered."""
    opener = opener or urllib.request.urlopen
    headers = {"Host": host}
    if header:
        key, _, value = header.partition(":")
        headers[key.strip()] = value.strip()
    tally = Counter()
    for _ in range(count):
        request = urllib.request.Request(f"http://{ip}/version", headers=headers)
        with opener(request, timeout=5) as response:
            info = json.loads(response.read().decode())
        tally[f"{info['version']} build {info['build']} ({info['track']})"] += 1
    for release, hits in tally.most_common():
        print(f"{hits:4d}  {release}")
    return tally


def parse_args(argv):
    choices = list(STRATEGIES)
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("deploy", "smoke"):
        cmd = sub.add_parser(name)
        cmd.add_argument("strategy", choices=choices + ["all"])
        if name == "deploy":
            cmd.add_argument("--image", required=True)
        cmd.add_argument("--expect-version")
        cmd.add_argument("--expect-build")
    sub.add_parser("rollback").add_argument("strategy", choices=choices + ["all"])
    sub.add_parser("promote").add_argument("strategy", choices=choices)
    sub.add_parser("status")
    cmd = sub.add_parser("traffic")
    cmd.add_argument("strategy", choices=choices)
    cmd.add_argument("--ip", required=True, help="ingress address, e.g. $(minikube ip)")
    cmd.add_argument("--count", type=int, default=20)
    cmd.add_argument("--header", help="extra header, e.g. 'X-Variant: B'")
    parser.add_argument("--timeout", default="180s", help="rollout timeout")
    return parser.parse_args(argv)


def main(argv=None, deployer=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "traffic":
        traffic(STRATEGIES[args.strategy]["host"], args.ip, args.count, args.header)
        return 0
    deployer = deployer or Deployer(Kubectl(), timeout=args.timeout)
    if args.command == "status":
        deployer.status()
        return 0
    if args.command == "promote":
        try:
            deployer.promote(args.strategy)
        except DeployError as exc:
            print(f"!! promote {args.strategy}: {exc}", file=sys.stderr)
            return 1
        return 0
    targets = list(STRATEGIES) if args.strategy == "all" else [args.strategy]
    failed = []
    for strategy in targets:
        try:
            if args.command == "deploy":
                deployer.deploy(strategy, args.image, args.expect_version, args.expect_build)
            elif args.command == "smoke":
                deployer.smoke(strategy, args.expect_version, args.expect_build)
            else:
                deployer.rollback(strategy)
        except DeployError as exc:
            print(f"!! {strategy}: {exc}", file=sys.stderr)
            failed.append(strategy)
    if failed:
        print(f"!! failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"== {args.command} succeeded: {', '.join(targets)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
