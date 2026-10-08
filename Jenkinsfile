// Jenkins BUILD and quality gate for ACEest Fitness & Gym.
// Runs on Linux, macOS or Windows agents. The agent needs Python 3.10+,
// Git and Docker on its PATH.
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    triggers {
        // Poll GitHub every 5 minutes; replace with a webhook if Jenkins is reachable.
        pollSCM('H/5 * * * *')
    }

    environment {
        IMAGE      = "aceest-fitness:${BUILD_NUMBER}"
        TEST_IMAGE = "aceest-fitness:${BUILD_NUMBER}-test"
    }

    stages {
        stage('Checkout') {
            steps {
                cleanWs()
                checkout scm
            }
        }

        stage('Clean Build Environment') {
            steps {
                script {
                    env.PY = isUnix() ? '.venv/bin/python' : '.venv\Scripts\python'
                    run "${isUnix() ? 'python3' : 'python'} -m venv .venv"
                    run "${env.PY} -m pip install --upgrade pip"
                    run "${env.PY} -m pip install -r requirements-dev.txt"
                }
            }
        }

        stage('Compile & Lint') {
            steps {
                script {
                    run "${env.PY} -m compileall -q app.py wsgi.py tests"
                    run "${env.PY} -m flake8 ."
                }
            }
        }

        stage('Unit Tests') {
            steps {
                script {
                    run "${env.PY} -m pytest -v --junitxml=test-results.xml " +
                        "--cov=app --cov=wsgi --cov-report=term-missing " +
                        "--cov-report=xml --cov-fail-under=90"
                }
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'test-results.xml'
                    archiveArtifacts artifacts: 'coverage.xml', allowEmptyArchive: true
                }
            }
        }

        stage('Docker Build') {
            steps {
                script {
                    run "docker build --no-cache -t ${env.IMAGE} ."
                }
            }
        }

        stage('Container Tests') {
            steps {
                script {
                    run "docker build --target test -t ${env.TEST_IMAGE} ."
                    run "docker run --rm ${env.TEST_IMAGE}"
                }
            }
        }
    }

    post {
        success { echo "BUILD passed: ${IMAGE}" }
        failure { echo 'BUILD failed - see the stage logs above.' }
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
