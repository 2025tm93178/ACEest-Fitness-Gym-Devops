// Jenkins CI/CD pipeline for ACEest Fitness & Gym.
//
// lint -> unit tests -> SonarQube + quality gate -> Docker image -> tests inside the image
// -> versioned build artifacts -> push to Docker Hub -> deploy to Kubernetes with the chosen
// strategy -> smoke test -> automatic rollback to the last stable version on failure.
//
// Agent needs: Python 3.10+, Git, Docker, kubectl (and minikube when images are not pushed).
// Jenkins needs: credentials 'dockerhub-creds' (Docker Hub username + access token);
// SonarQube Scanner plugin with a server named 'SonarQube' and a scanner tool 'SonarScanner'.
// Works on Linux, macOS and Windows agents: shell steps go through run() (sh or bat).
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20', artifactNumToKeepStr: '10'))
    }

    triggers {
        // Poll GitHub every 5 minutes and build when main changes.
        pollSCM('H/5 * * * *')
    }

    parameters {
        // Polled builds use the first choice of each parameter.
        choice(name: 'DEPLOY_STRATEGY',
               choices: ['all', 'rolling', 'blue-green', 'canary', 'ab-testing', 'shadow', 'none'],
               description: 'Kubernetes deployment strategy (all = every strategy in turn)')
        booleanParam(name: 'RUN_SONAR', defaultValue: true,
                     description: 'Run SonarQube analysis and enforce the quality gate')
        booleanParam(name: 'PUSH_IMAGE', defaultValue: true,
                     description: 'Push the image to Docker Hub (otherwise load it into minikube)')
        string(name: 'DOCKERHUB_REPO', defaultValue: 'aceest-fitness',
               description: 'Docker Hub repository name under the credentials\' account')
        string(name: 'KUBECONFIG_CREDENTIAL', defaultValue: '',
               description: 'Optional secret-file credential with a kubeconfig; empty = agent default')
        booleanParam(name: 'SIMULATE_FAILURE', defaultValue: false,
                     description: 'Demo: make the smoke test fail to show the automatic rollback')
    }

    stages {
        stage('Checkout') {
            steps {
                cleanWs()
                checkout scm
                script {
                    env.APP_VERSION = readFile('VERSION').trim()
                    env.IMAGE_TAG   = "${env.APP_VERSION}-b${env.BUILD_NUMBER}"
                    env.LOCAL_IMAGE = "aceest-fitness:${env.IMAGE_TAG}"
                    env.TEST_IMAGE  = "aceest-fitness:${env.IMAGE_TAG}-test"
                    currentBuild.displayName = "#${env.BUILD_NUMBER} v${env.IMAGE_TAG}"
                }
            }
        }

        stage('Clean Build Environment') {
            steps {
                script {
                    env.PY = isUnix() ? '.venv/bin/python' : '.venv\\Scripts\\python'
                    run "${isUnix() ? 'python3' : 'python'} -m venv .venv"
                    run "${env.PY} -m pip install --upgrade pip"
                    run "${env.PY} -m pip install -r requirements-dev.txt"
                }
            }
        }

        stage('Compile & Lint') {
            steps {
                script {
                    run "${env.PY} -m compileall -q app.py ACEest_Fitness.py k8s tests"
                    run "${env.PY} -m flake8 ."
                }
            }
        }

        stage('Unit Tests') {
            steps {
                script {
                    run "${env.PY} -m pytest -v --junitxml=test-results.xml " +
                        "--cov=app --cov=ACEest_Fitness --cov=deployctl " +
                        "--cov-report=term-missing --cov-report=xml --cov-fail-under=90"
                }
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'test-results.xml'
                    archiveArtifacts artifacts: 'coverage.xml', allowEmptyArchive: true
                }
            }
        }

        stage('SonarQube Analysis') {
            when { expression { params.RUN_SONAR } }
            steps {
                script {
                    def home = tool 'SonarScanner'
                    def scanner = isUnix() ? "${home}/bin/sonar-scanner"
                                           : "${home}\\bin\\sonar-scanner.bat"
                    withSonarQubeEnv('SonarQube') {
                        run "${scanner} -Dsonar.projectVersion=${env.IMAGE_TAG}"
                    }
                }
            }
        }

        stage('Quality Gate') {
            when { expression { params.RUN_SONAR } }
            steps {
                // Needs a SonarQube webhook to <jenkins-url>/sonarqube-webhook/
                timeout(time: 10, unit: 'MINUTES') {
                    waitForQualityGate abortPipeline: true
                }
            }
        }

        stage('Docker Build') {
            steps {
                script {
                    run "docker build --no-cache --build-arg APP_VERSION=${env.APP_VERSION} " +
                        "--build-arg APP_BUILD=${env.BUILD_NUMBER} -t ${env.LOCAL_IMAGE} ."
                }
            }
        }

        stage('Container Tests') {
            steps {
                script {
                    // Pytest inside the containerised environment, with the 90% coverage gate.
                    run "docker build --target test -t ${env.TEST_IMAGE} ."
                    run "docker run --rm ${env.TEST_IMAGE}"
                }
            }
        }

        stage('Build Artifacts') {
            steps {
                script {
                    def commit = isUnix() ? sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
                                          : bat(script: '@git rev-parse HEAD', returnStdout: true).trim()
                    writeFile file: 'dist/build-info.json', text: """{
  "application": "ACEest Fitness & Gym",
  "version": "${env.APP_VERSION}",
  "build": "${env.BUILD_NUMBER}",
  "image_tag": "${env.IMAGE_TAG}",
  "commit": "${commit}",
  "built_at": "${new Date().format("yyyy-MM-dd'T'HH:mm:ssZ")}"
}
"""
                    run "git archive --format=zip --prefix=aceest-fitness-${env.IMAGE_TAG}/ " +
                        "-o dist/aceest-fitness-${env.IMAGE_TAG}.zip HEAD"
                }
                archiveArtifacts artifacts: 'dist/*', fingerprint: true
            }
        }

        stage('Push to Docker Hub') {
            when { expression { params.PUSH_IMAGE } }
            steps {
                withCredentials([usernamePassword(credentialsId: 'dockerhub-creds',
                                                  usernameVariable: 'DH_USER',
                                                  passwordVariable: 'DH_TOKEN')]) {
                    script {
                        env.REMOTE_IMAGE = "${env.DH_USER}/${params.DOCKERHUB_REPO}"
                        if (isUnix()) {
                            sh 'echo "$DH_TOKEN" | docker login -u "$DH_USER" --password-stdin'
                        } else {
                            bat '@echo %DH_TOKEN%| docker login -u %DH_USER% --password-stdin'
                        }
                        // One image per build, plus moving tags for the release and the latest build.
                        for (tag in [env.IMAGE_TAG, env.APP_VERSION, 'latest']) {
                            run "docker tag ${env.LOCAL_IMAGE} ${env.REMOTE_IMAGE}:${tag}"
                            run "docker push ${env.REMOTE_IMAGE}:${tag}"
                        }
                        run 'docker logout'
                    }
                }
            }
        }

        stage('Deploy to Kubernetes') {
            when { expression { params.DEPLOY_STRATEGY != 'none' } }
            steps {
                script {
                    def image = params.PUSH_IMAGE ? "${env.REMOTE_IMAGE}:${env.IMAGE_TAG}" : env.LOCAL_IMAGE
                    if (!params.PUSH_IMAGE) {
                        run "minikube image load ${env.LOCAL_IMAGE}"
                    }
                    def expect = params.SIMULATE_FAILURE ? '0.0.0-simulated-failure' : env.APP_VERSION
                    // deployctl smoke tests every rollout and rolls back automatically on failure.
                    def deploy = {
                        run "${env.PY} k8s/deployctl.py deploy ${params.DEPLOY_STRATEGY} " +
                            "--image ${image} --expect-version ${expect} " +
                            "--expect-build ${env.BUILD_NUMBER}"
                        run "${env.PY} k8s/deployctl.py status"
                    }
                    if (params.KUBECONFIG_CREDENTIAL?.trim()) {
                        withCredentials([file(credentialsId: params.KUBECONFIG_CREDENTIAL.trim(),
                                              variable: 'KUBECONFIG')]) {
                            deploy()
                        }
                    } else {
                        deploy()
                    }
                }
            }
        }
    }

    post {
        success {
            echo "Pipeline passed: v${env.IMAGE_TAG} built, tested and deployed (${params.DEPLOY_STRATEGY})"
        }
        failure {
            echo 'Pipeline failed - see the stage logs. A failed deployment has already been ' +
                 'rolled back to the last stable version.'
        }
    }
}

// Run a shell command with sh on Unix agents and bat on Windows agents.
def run(String command) {
    if (isUnix()) {
        sh command
    } else {
        bat command
    }
}
