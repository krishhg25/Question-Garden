// Pipeline from SCM; Script Path: Jenkinsfile (independent app repository).
// Agent prerequisites: Python 3.12+, Node.js 22+, Git, Tesseract + English data.
// Docker is needed only when BUILD_CONTAINERS is selected. No cloud deployment.
pipeline {
    agent any
    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }
    parameters {
        booleanParam(name: 'BUILD_CONTAINERS', defaultValue: false,
            description: 'Build Docker images on a Docker-enabled agent; no deploy or push.')
    }
    environment {
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
        PYTHONIOENCODING = 'utf-8'
        PYTHONUTF8 = '1'
        ALLOW_DEMO_AUTH = 'false'
        OLLAMA_URL = ''
    }
    stages {
        stage('Checkout') {
            steps { checkout scm }
        }
        stage('Install dependencies') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''set -eu
python3 -m venv .ci-venv
.ci-venv/bin/python -m pip install -r backend/requirements.lock
'''
                    } else {
                        bat '''@echo off
python -m venv .ci-venv
if errorlevel 1 exit /b 1
.ci-venv\\Scripts\\python.exe -m pip install -r backend\\requirements.lock
if errorlevel 1 exit /b 1
'''
                    }
                }
                dir('frontend') {
                    script {
                        if (isUnix()) { sh 'npm ci' }
                        else { bat 'call npm ci' }
                    }
                }
            }
        }
        stage('Backend tests') {
            steps {
                dir('backend') {
                    script {
                        if (isUnix()) { sh '../.ci-venv/bin/python -m pytest -q --junitxml=../ci-results/pytest.xml' }
                        else { bat '..\\.ci-venv\\Scripts\\python.exe -m pytest -q --junitxml=..\\ci-results\\pytest.xml' }
                    }
                }
            }
            post { always { junit testResults: 'ci-results/pytest.xml', allowEmptyResults: true } }
        }
        stage('Frontend build') {
            steps {
                dir('frontend') {
                    script {
                        if (isUnix()) { sh 'npm run build' }
                        else { bat 'call npm run build' }
                    }
                }
            }
        }
        stage('OCR and API evidence') {
            steps {
                script {
                    if (isUnix()) { sh '.ci-venv/bin/python deploy/ci_evidence.py' }
                    else { bat '.ci-venv\\Scripts\\python.exe deploy\\ci_evidence.py' }
                }
            }
        }
        stage('Docker image build') {
            when { expression { params.BUILD_CONTAINERS } }
            steps {
                script {
                    if (isUnix()) {
                        sh '''set -eu
docker version
docker build -t question-garden-backend:ci-$BUILD_NUMBER backend
docker build -t question-garden-frontend:ci-$BUILD_NUMBER frontend
'''
                    } else {
                        bat '''@echo off
docker version
if errorlevel 1 exit /b 1
docker build -t question-garden-backend:ci-%BUILD_NUMBER% backend
if errorlevel 1 exit /b 1
docker build -t question-garden-frontend:ci-%BUILD_NUMBER% frontend
if errorlevel 1 exit /b 1
'''
                    }
                }
            }
        }
        stage('Archive evidence') {
            steps {
                archiveArtifacts artifacts: 'ci-results/**,frontend/dist/**,Jenkinsfile', fingerprint: true
            }
        }
    }
    post {
        always {
            archiveArtifacts artifacts: 'ci-results/**', allowEmptyArchive: true
        }
    }
}
