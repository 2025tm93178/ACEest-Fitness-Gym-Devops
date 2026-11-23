#!/usr/bin/env bash
# One-shot setup of the BITS lab VM (Rocky/RHEL Linux) for the ACEest CI/CD pipeline.
#
#   VM:        Docker access, kubectl, minikube + NGINX ingress, cluster access for Jenkins,
#              *.aceest.local host names
#   SonarQube: container, admin password, analysis token, webhook to Jenkins
#   Jenkins:   plugins, credentials (dockerhub-creds, sonar-token), SonarQube server
#              'SonarQube', scanner tool 'SonarScanner', pipeline job, first build
#
# Usage (as your normal user, NOT root; sudo is used where needed):
#   bash setup-lab-vm.sh             # everything
#   bash setup-lab-vm.sh --ci-only   # only SonarQube + Jenkins configuration
#   bash setup-lab-vm.sh --no-build  # do not start a build at the end
#
# It asks for: your Jenkins login, your Docker Hub access token, and a SonarQube admin
# password. Safe to run again: every step checks what is already done.
set -euo pipefail

# ---------------------------------------------------------------- settings
JENKINS_URL="${JENKINS_URL:-http://localhost:8080}"
SONAR_URL="${SONAR_URL:-http://localhost:9000}"
JOB_NAME="${JOB_NAME:-aceest-fitness-2025tm93178}"
REPO_URL="${REPO_URL:-https://github.com/2025tm93178/ACEest-Fitness-Gym-Devops.git}"
DOCKERHUB_USER="${DOCKERHUB_USER:-2025tm93178anwesa}"
SCANNER_VERSION="${SCANNER_VERSION:-8.5.0.16571}"
SONAR_IMAGE="${SONAR_IMAGE:-sonarqube:lts-community}"
MINIKUBE_CPUS="${MINIKUBE_CPUS:-2}"
MINIKUBE_MEMORY="${MINIKUBE_MEMORY:-3072}"
HOSTS="rolling.aceest.local bluegreen.aceest.local canary.aceest.local ab.aceest.local shadow.aceest.local"

CI_ONLY=0 RUN_BUILD=1
for arg in "$@"; do
    case "$arg" in
        --ci-only) CI_ONLY=1 ;;
        --no-build) RUN_BUILD=0 ;;
        -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 1 ;;
    esac
done

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32mok\033[0m %s\n' "$*"; }
warn() { printf '    \033[33m!!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }
json() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)"; }
b64()  { printf '%s' "$1" | base64 | tr -d '\n'; }

# ---------------------------------------------------------------- questions first
step "Details needed (input is hidden)"
JENKINS_ADMIN="${JENKINS_ADMIN:-}"
[ -n "$JENKINS_ADMIN" ] || read -rp "    Jenkins username [cloud]: " JENKINS_ADMIN
JENKINS_ADMIN="${JENKINS_ADMIN:-cloud}"
[ -n "${JENKINS_PASSWORD:-}" ] || { read -rsp "    Jenkins password: " JENKINS_PASSWORD; echo; }
[ -n "${DOCKERHUB_TOKEN:-}" ] || { read -rsp "    Docker Hub access token (dckr_pat_...): " DOCKERHUB_TOKEN; echo; }
if [ -z "${SONAR_PASSWORD:-}" ]; then
    echo "    SonarQube admin password: the one you already set, or a NEW one"
    echo "    (12+ characters with upper case, lower case, a digit and a symbol)."
    read -rsp "    SonarQube admin password: " SONAR_PASSWORD; echo
fi
[ ${#SONAR_PASSWORD} -ge 12 ] || die "the SonarQube password must be at least 12 characters"

if [ "$CI_ONLY" = 0 ]; then
    [ "$(id -u)" -ne 0 ] || die "run this as your normal user, not root (minikube refuses root)"
    sudo -v || die "this script needs sudo"

    # ------------------------------------------------------------ 1. checks
    step "1/9 Checking the VM"
    command -v git >/dev/null || sudo dnf -y install git
    command -v python3 >/dev/null || sudo dnf -y install python3
    python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || die "python3 3.9+ is required"
    ok "$(git --version), $(python3 -V), $(nproc) CPUs, $(free -m | awk '/Mem:/{print $2}') MB RAM"

    # ------------------------------------------------------------ 2. docker
    step "2/9 Docker"
    if ! command -v docker >/dev/null; then
        sudo dnf -y install dnf-plugins-core
        sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
        sudo dnf -y install docker-ce docker-ce-cli containerd.io
    fi
    sudo systemctl enable --now docker >/dev/null 2>&1 || true
    if id jenkins >/dev/null 2>&1 && ! id -nG jenkins | grep -qw docker; then
        sudo usermod -aG docker jenkins
        sudo systemctl restart jenkins
        ok "added jenkins to the docker group and restarted Jenkins"
    fi
    if ! docker ps >/dev/null 2>&1; then
        id -nG "$USER" | grep -qw docker || sudo usermod -aG docker "$USER"
        die "docker is not usable by $USER yet: log out and in (or run 'newgrp docker'), then run this script again"
    fi
    ok "$(docker --version)"

    # ------------------------------------------------------------ 3. kubectl + minikube
    step "3/9 kubectl and minikube"
    tmp="$(mktemp -d)"
    if ! command -v kubectl >/dev/null; then
        ver="$(curl -fsSL https://dl.k8s.io/release/stable.txt)"
        curl -fsSL -o "$tmp/kubectl" "https://dl.k8s.io/release/$ver/bin/linux/amd64/kubectl"
        sudo install -m 0755 "$tmp/kubectl" /usr/local/bin/kubectl
    fi
    if ! command -v minikube >/dev/null; then
        curl -fsSL -o "$tmp/minikube" https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
        sudo install -m 0755 "$tmp/minikube" /usr/local/bin/minikube
    fi
    rm -rf "$tmp"
    # sudo (secure_path) and the Jenkins service do not search /usr/local/bin on Rocky.
    for t in kubectl minikube; do
        p="$(command -v "$t")"
        [ "$p" = "/usr/bin/$t" ] || sudo ln -sf "$p" "/usr/bin/$t"
    done
    ok "kubectl and $(minikube version --short) installed"

    # ------------------------------------------------------------ 4. cluster + ingress
    step "4/9 Minikube cluster and NGINX ingress"
    minikube status >/dev/null 2>&1 \
        || minikube start --driver=docker --cpus="$MINIKUBE_CPUS" --memory="$MINIKUBE_MEMORY"
    minikube addons enable ingress >/dev/null
    kubectl wait -n ingress-nginx --for=condition=ready pod \
        -l app.kubernetes.io/component=controller --timeout=300s >/dev/null
    MINIKUBE_IP="$(minikube ip)"
    ok "cluster up, ingress ready, minikube ip = $MINIKUBE_IP"

    # ------------------------------------------------------------ 5. kubeconfig for Jenkins
    step "5/9 Cluster access for Jenkins"
    if id jenkins >/dev/null 2>&1 && [ "$USER" != jenkins ]; then
        jhome="$(getent passwd jenkins | cut -d: -f6)"
        kubectl config view --flatten --minify > /tmp/aceest-kubeconfig
        sudo mkdir -p "$jhome/.kube"
        sudo install -m 0600 -o jenkins -g "$(id -gn jenkins)" /tmp/aceest-kubeconfig "$jhome/.kube/config"
        rm -f /tmp/aceest-kubeconfig
        sudo -u jenkins kubectl get nodes >/dev/null || die "the jenkins user cannot reach the cluster"
        sudo -u jenkins docker ps >/dev/null || die "the jenkins user cannot use docker (restart Jenkins)"
        ok "jenkins can use docker and reach the cluster"
    fi

    # ------------------------------------------------------------ 6. hosts
    step "6/9 Host names for the five strategies"
    sudo sed -i '/aceest\.local/d' /etc/hosts
    echo "$MINIKUBE_IP $HOSTS" | sudo tee -a /etc/hosts >/dev/null
    ok "/etc/hosts: $MINIKUBE_IP -> $HOSTS"

    # ------------------------------------------------------------ SonarQube container
    if [ "$(sysctl -n vm.max_map_count)" -lt 524288 ]; then
        sudo sysctl -qw vm.max_map_count=524288
        echo "vm.max_map_count=524288" | sudo tee /etc/sysctl.d/99-sonarqube.conf >/dev/null
    fi
    if ! docker ps -a --format '{{.Names}}' | grep -qx sonarqube; then
        docker run -d --name sonarqube --restart unless-stopped -p 9000:9000 \
            -v sonarqube_data:/opt/sonarqube/data -v sonarqube_extensions:/opt/sonarqube/extensions \
            "$SONAR_IMAGE" >/dev/null
    fi
    docker start sonarqube >/dev/null
fi

# ---------------------------------------------------------------- 7. SonarQube
step "7/9 SonarQube"
printf '    waiting for SonarQube'
for _ in $(seq 1 120); do
    curl -fs "$SONAR_URL/api/system/status" 2>/dev/null | grep -q '"status":"UP"' && break
    printf '.'; sleep 5
done
echo
curl -fs "$SONAR_URL/api/system/status" | grep -q '"status":"UP"' \
    || die "SonarQube is not up at $SONAR_URL (docker logs sonarqube)"

valid() { curl -s -u "admin:$1" "$SONAR_URL/api/authentication/validate" | json 'd["valid"]'; }
if [ "$(valid "$SONAR_PASSWORD")" != True ]; then
    [ "$(valid admin)" = True ] || die "wrong SonarQube admin password (and it is no longer admin/admin)"
    curl -fs -u admin:admin -X POST "$SONAR_URL/api/users/change_password" \
        --data-urlencode login=admin --data-urlencode previousPassword=admin \
        --data-urlencode "password=$SONAR_PASSWORD" \
        || die "SonarQube rejected the new password (needs upper, lower, digit and symbol)"
    ok "admin password set"
fi
SONAR_TOKEN="$(curl -fs -u "admin:$SONAR_PASSWORD" -X POST "$SONAR_URL/api/user_tokens/generate" \
    --data-urlencode "name=jenkins-$(date +%Y%m%d%H%M%S)" \
    --data-urlencode type=GLOBAL_ANALYSIS_TOKEN | json 'd["token"]')"
ok "analysis token created"

if [ -z "${WEBHOOK_URL:-}" ]; then
    VM_IP="$(ip route get 1.1.1.1 | awk '{for (i = 1; i < NF; i++) if ($i == "src") {print $(i + 1); exit}}')"
    WEBHOOK_URL="http://$VM_IP:8080/sonarqube-webhook/"
fi
hooks="$(curl -fs -u "admin:$SONAR_PASSWORD" "$SONAR_URL/api/webhooks/list")"
hook_key="$(printf '%s' "$hooks" | json 'next((w["key"] for w in d["webhooks"] if w["name"] == "Jenkins"), "")')"
if [ -n "$hook_key" ]; then
    curl -fs -u "admin:$SONAR_PASSWORD" -X POST "$SONAR_URL/api/webhooks/update" \
        --data-urlencode "webhook=$hook_key" --data-urlencode name=Jenkins \
        --data-urlencode "url=$WEBHOOK_URL"
else
    curl -fs -u "admin:$SONAR_PASSWORD" -X POST "$SONAR_URL/api/webhooks/create" \
        --data-urlencode name=Jenkins --data-urlencode "url=$WEBHOOK_URL" >/dev/null
fi
ok "webhook 'Jenkins' -> $WEBHOOK_URL"

# The Quality Gate stage waits for this webhook, so check SonarQube can reach Jenkins.
reach() { rc=0; docker exec sonarqube wget -q -T 5 -O /dev/null "$WEBHOOK_URL" >/dev/null 2>&1 || rc=$?; [ "$rc" = 0 ] || [ "$rc" = 8 ]; }
if [ "$CI_ONLY" = 0 ]; then
    if ! reach && systemctl is-active -q firewalld; then
        sudo firewall-cmd -q --permanent --add-port=8080/tcp && sudo firewall-cmd -q --reload
        ok "opened port 8080 in the firewall for the SonarQube webhook"
    fi
    reach && ok "SonarQube can reach Jenkins" \
        || warn "SonarQube cannot reach $WEBHOOK_URL: the Quality Gate stage will time out"
fi

# ---------------------------------------------------------------- 8. Jenkins
step "8/9 Jenkins configuration"
COOKIES="$(mktemp)"; trap 'rm -f "$COOKIES"' EXIT
jcurl() { curl -s -g -u "$JENKINS_ADMIN:$JENKINS_PASSWORD" -b "$COOKIES" -c "$COOKIES" "$@"; }
wait_jenkins() {
    printf '    waiting for Jenkins'
    for _ in $(seq 1 120); do
        [ "$(curl -s -o /dev/null -w '%{http_code}' "$JENKINS_URL/login")" = 200 ] && { echo; return 0; }
        printf '.'; sleep 5
    done
    echo; die "Jenkins is not answering at $JENKINS_URL"
}
crumb_header() {
    local c
    c="$(jcurl "$JENKINS_URL/crumbIssuer/api/json" 2>/dev/null || true)"
    printf '%s' "$c" | json 'd["crumbRequestField"] + ":" + d["crumb"]' 2>/dev/null || true
}
groovy() {  # groovy FILE -> prints the script's output, fails on a Groovy error
    local h out
    h="$(crumb_header)"
    out="$(jcurl ${h:+-H "$h"} --data-urlencode "script@$1" "$JENKINS_URL/scriptText")"
    printf '%s\n' "$out"
    ! printf '%s' "$out" | grep -qE 'Exception|ERROR|startup failed'
}

wait_jenkins
who="$(jcurl "$JENKINS_URL/whoAmI/api/json")"
[ "$(printf '%s' "$who" | json 'd.get("authenticated") and not d.get("anonymous")' 2>/dev/null)" = True ] \
    || die "Jenkins login failed for user '$JENKINS_ADMIN' (check the username and password)"
ok "logged in to Jenkins as $JENKINS_ADMIN"

G="$(mktemp -d)"
cat > "$G/plugins.groovy" <<'EOF'
import jenkins.model.Jenkins
def j = Jenkins.get()
def wanted = ['sonar', 'workflow-aggregator', 'git', 'credentials-binding', 'plain-credentials',
              'ws-cleanup', 'timestamper', 'junit', 'pipeline-stage-view']
def missing = wanted.findAll { j.pluginManager.getPlugin(it) == null }
if (missing) {
    j.updateCenter.updateAllSites()
    missing.each { name ->
        def p = j.updateCenter.getPlugin(name)
        if (p == null) { println "PLUGIN_UNAVAILABLE ${name}" }
        else { p.deploy(true).get(); println "PLUGIN_INSTALLED ${name}" }
    }
    println 'RESTART_NEEDED'
} else {
    println 'PLUGINS_OK'
}
EOF
out="$(groovy "$G/plugins.groovy")" || die "installing plugins failed: $out"
printf '%s\n' "$out" | sed 's/^/    /'
if printf '%s' "$out" | grep -q RESTART_NEEDED; then
    h="$(crumb_header)"
    jcurl ${h:+-H "$h"} -X POST "$JENKINS_URL/safeRestart" -o /dev/null
    sleep 10
    wait_jenkins
    : > "$COOKIES"
    ok "plugins installed, Jenkins restarted"
fi

cat > "$G/config.groovy" <<EOF
import jenkins.model.Jenkins
import com.cloudbees.plugins.credentials.CredentialsScope
import com.cloudbees.plugins.credentials.SystemCredentialsProvider
import com.cloudbees.plugins.credentials.domains.Domain
import com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl
import org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl
import hudson.util.Secret
import hudson.tools.InstallSourceProperty
import hudson.plugins.sonar.SonarGlobalConfiguration
import hudson.plugins.sonar.SonarInstallation
import hudson.plugins.sonar.SonarRunnerInstallation
import hudson.plugins.sonar.SonarRunnerInstaller
import org.jenkinsci.plugins.structs.describable.DescribableModel

def s = { String v -> new String(v.decodeBase64(), 'UTF-8') }
def j = Jenkins.get()

// ---- credentials (created or replaced)
def store = SystemCredentialsProvider.getInstance().getStore()
def domain = Domain.global()
def put = { c ->
    def old = store.getCredentials(domain).find { it.id == c.id }
    if (old) { store.updateCredentials(domain, old, c) } else { store.addCredentials(domain, c) }
    println "CREDENTIAL \${c.id}"
}
put(new UsernamePasswordCredentialsImpl(CredentialsScope.GLOBAL, 'dockerhub-creds',
        'Docker Hub', s('$(b64 "$DOCKERHUB_USER")'), s('$(b64 "$DOCKERHUB_TOKEN")')))
put(new StringCredentialsImpl(CredentialsScope.GLOBAL, 'sonar-token', 'SonarQube token',
        Secret.fromString(s('$(b64 "$SONAR_TOKEN")'))))

// ---- SonarQube server 'SonarQube' with build-environment injection
def sonar = j.getDescriptorByType(SonarGlobalConfiguration)
def server = DescribableModel.of(SonarInstallation).instantiate(
        [name: 'SonarQube', serverUrl: s('$(b64 "$SONAR_URL")'), credentialsId: 'sonar-token'])
def servers = sonar.installations.findAll { it.name != 'SonarQube' } + [server]
sonar.setInstallations(servers as SonarInstallation[])
sonar.setBuildWrapperEnabled(true)
sonar.save()
println "SONAR_SERVER \${server.name} -> \${server.serverUrl}"

// ---- scanner tool 'SonarScanner' (installed automatically on first use)
def tools = j.getDescriptorByType(SonarRunnerInstallation.DescriptorImpl)
if (!tools.installations.find { it.name == 'SonarScanner' }) {
    def tool = new SonarRunnerInstallation('SonarScanner', '',
            [new InstallSourceProperty([new SonarRunnerInstaller('$SCANNER_VERSION')])])
    tools.setInstallations((tools.installations.toList() + [tool]) as SonarRunnerInstallation[])
    tools.save()
}
println "SCANNER_TOOL SonarScanner"

// ---- pipeline job from SCM
def name = s('$(b64 "$JOB_NAME")')
if (j.getItem(name) == null) {
    def xml = """<flow-definition plugin="workflow-job">
  <description>ACEest Fitness &amp; Gym CI/CD pipeline (Assignment 2)</description>
  <keepDependencies>false</keepDependencies>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition" plugin="workflow-cps">
    <scm class="hudson.plugins.git.GitSCM" plugin="git">
      <configVersion>2</configVersion>
      <userRemoteConfigs><hudson.plugins.git.UserRemoteConfig>
        <url>\${s('$(b64 "$REPO_URL")')}</url>
      </hudson.plugins.git.UserRemoteConfig></userRemoteConfigs>
      <branches><hudson.plugins.git.BranchSpec><name>*/main</name></hudson.plugins.git.BranchSpec></branches>
      <doGenerateSubmoduleConfigurations>false</doGenerateSubmoduleConfigurations>
      <submoduleCfg class="empty-list"/>
      <extensions/>
    </scm>
    <scriptPath>Jenkinsfile</scriptPath>
    <lightweight>true</lightweight>
  </definition>
  <disabled>false</disabled>
</flow-definition>"""
    j.createProjectFromXML(name, new ByteArrayInputStream(xml.getBytes('UTF-8')))
    println "JOB_CREATED \${name}"
} else {
    println "JOB_EXISTS \${name}"
}
println 'CONFIG_OK'
EOF
out="$(groovy "$G/config.groovy")" || { rm -rf "$G"; die "Jenkins configuration failed: $out"; }
rm -rf "$G"
printf '%s\n' "$out" | grep -E 'CREDENTIAL|SONAR_SERVER|SCANNER_TOOL|JOB_' | sed 's/^/    ok /'
printf '%s' "$out" | grep -q CONFIG_OK || die "Jenkins configuration did not finish: $out"

# ---------------------------------------------------------------- 9. first build
step "9/9 Build"
JOB_URL="$JENKINS_URL/job/$JOB_NAME"
if [ "$RUN_BUILD" = 0 ]; then
    ok "skipped (--no-build). Start it from $JOB_URL"
else
    last="$(jcurl "$JOB_URL/api/json?tree=lastBuild[number]" | json '(d.get("lastBuild") or {}).get("number", 0)')"
    h="$(crumb_header)"
    code="$(jcurl ${h:+-H "$h"} -o /dev/null -w '%{http_code}' -X POST "$JOB_URL/buildWithParameters")"
    case "$code" in
        2*) ;;
        *) h="$(crumb_header)"; jcurl ${h:+-H "$h"} -o /dev/null -X POST "$JOB_URL/build" ;;
    esac
    printf '    build started, waiting (the first one takes 10-15 minutes)'
    result=""
    for _ in $(seq 1 360); do
        sleep 10; printf '.'
        info="$(jcurl "$JOB_URL/lastBuild/api/json?tree=number,result,building" || true)"
        num="$(printf '%s' "$info" | json 'd.get("number", 0)' 2>/dev/null || echo 0)"
        if [ "$num" -gt "$last" ] && [ "$(printf '%s' "$info" | json 'd["building"]')" = False ]; then
            result="$(printf '%s' "$info" | json 'd["result"]')"; break
        fi
    done
    echo
    if [ "$result" = SUCCESS ]; then
        ok "build #$num SUCCESS: $JOB_URL/$num/"
    else
        warn "build #$num finished with ${result:-no result yet}: $JOB_URL/$num/console"
        warn "paste the end of that console output to get help"
    fi
fi

cat <<EOF

  Done.
    Jenkins job : $JOB_URL
    SonarQube   : $SONAR_URL  (login: admin)
    Docker Hub  : https://hub.docker.com/r/$DOCKERHUB_USER/aceest-fitness/tags
EOF
[ "$CI_ONLY" = 1 ] || echo "    Minikube IP : $MINIKUBE_IP   (endpoints: http://<strategy>.aceest.local/version)"
