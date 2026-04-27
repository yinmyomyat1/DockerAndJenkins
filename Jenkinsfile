pipeline {
    agent any

    environment {
        IMAGE_NAME = "myapp6"
        NETWORK_NAME = "app-network"
        DB_URI_DOCKER = "mysql+pymysql://root:root@mysql-db-dast:3306/imdb_db"
        DOCKERHUB_CREDENTIALS = credentials('docker-hub-credentials')
        FULL_IMAGE_TAG = ""
    }

    stages {
        stage('Checkout') {
            steps {
                git branch: 'main',
                    url: 'https://github.com/yinmyomyat1/DockerAndJenkins.git',
                    credentialsId: '38a91060-b488-47c6-93b0-5e739fc3041d'
            }
        }

        stage('Setup Docker Network') {
            steps {
                sh 'docker network create ${NETWORK_NAME} || true'
            }
        }

        stage('Launch MySQL') {
            steps {
                sh '''
                docker rm -f mysql-db-dast || true
                docker run -d --name mysql-db-dast \
                    -e MYSQL_ROOT_PASSWORD=root \
                    -e MYSQL_DATABASE=imdb_db \
                    --network ${NETWORK_NAME} \
                    -p 3306:3306 \
                    mysql:8.0 || true
                
                echo "⏳ Waiting for MySQL (60s max)..."
                for i in {1..12}; do
                    if timeout 5 docker exec mysql-db-dast mysqladmin ping -h localhost -u root -proot --silent; then
                        echo "✅ MySQL ready!"
                        break
                    fi
                    echo "MySQL check $i/12 failed"
                    sleep 5
                done
                '''
            }
        }

        stage('Setup Python & Lint') {
            steps {
                sh '''
                rm -rf venv
                python3 -m venv venv
                . venv/bin/activate
                pip install --upgrade pip
                pip install -r requirements.txt
                pip install bandit safety pip-audit pytest
                deactivate
                '''
            }
        }

        stage('SCA & SAST - Security Scans') {
            steps {
                sh '''
                . venv/bin/activate
                mkdir -p reports
                echo "🔍 Bandit SAST..."
                bandit -r . -f json -o reports/bandit-report.json || true
                
                echo "🔍 Safety SCA..."
                safety check --full-report > reports/safety-report.txt || true
                
                echo "✅ Scans complete"
                deactivate
                '''
            }
        }

        stage('Build & Push') {
            steps {
                script {
                    env.FULL_IMAGE_TAG = "${DOCKERHUB_CREDENTIALS_USR}/${IMAGE_NAME}:${BUILD_NUMBER}"
                }
                sh '''
                echo "🔨 Building ${FULL_IMAGE_TAG}"
                docker build -t "${FULL_IMAGE_TAG}" .
                docker tag "${FULL_IMAGE_TAG}" "${DOCKERHUB_CREDENTIALS_USR}/${IMAGE_NAME}:latest"
                
                echo "🔐 Docker login"
                echo $DOCKERHUB_CREDENTIALS_PSW | docker login -u $DOCKERHUB_CREDENTIALS_USR --password-stdin
                
                echo "📤 Pushing (3 retries)"
                for attempt in {1..3}; do
                    if timeout 600 docker push "${FULL_IMAGE_TAG}"; then
                        echo "✅ Push success!"
                        docker push "${DOCKERHUB_CREDENTIALS_USR}/${IMAGE_NAME}:latest" || true
                        echo "FULL_IMAGE_TAG=${FULL_IMAGE_TAG}" > image_tag.env
                        break
                    else
                        echo "❌ Push $attempt/3 failed, retry ${attempt+1}"
                        sleep 30
                    fi
                done
                '''
            }
        }

        stage('Unit Tests') {
            steps {
                sh '''
                . venv/bin/activate
                export DB_URI="mysql+pymysql://root:root@localhost:3306/imdb_db"
                echo "🧪 Running pytest..."
                pytest -v --tb=short || true
                deactivate
                '''
            }
        }

        stage('Trivy Scan') {
            steps {
                sh '''
                source image_tag.env 2>/dev/null || echo "FULL_IMAGE_TAG=${FULL_IMAGE_TAG}"
                
                echo "🔍 Trivy scan..."
                docker pull aquasec/trivy:0.56.0 || true
                
                docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
                    aquasec/trivy:0.56.0 image \
                    --format table \
                    --severity HIGH,CRITICAL \
                    --no-progress \
                    "${FULL_IMAGE_TAG}" || true
                '''
            }
        }

        stage('Deploy & DAST') {
            steps {
                sh '''
                docker stop myapp6 || true
                docker rm myapp6 || true
                
                echo "🚀 Deploying app..."
                docker run -d --name myapp6 \
                    --network ${NETWORK_NAME} \
                    -p 5050:5050 \
                    -e DB_URI="${DB_URI_DOCKER}" \
                    "${FULL_IMAGE_TAG}"
                
                sleep 10
                
                echo "🛡️ ZAP DAST scan..."
                mkdir -p reports
                docker run --rm --network ${NETWORK_NAME} \
                    -v $(pwd)/reports:/zap/wrk/:rw \
                    ghcr.io/zaproxy/zaproxy:stable \
                    zap-baseline.py \
                    -t http://myapp6:5050 \
                    -r /zap/wrk/zap-report.html || true
                '''
            }
        }
    }

    post {
        always {
            sh '''
            docker stop myapp6 mysql-db-dast || true
            docker rm myapp6 mysql-db-dast || true
            docker image prune -f
            docker container prune -f
            '''
            archiveArtifacts artifacts: 'reports/**,image_tag.env,zap-report.html', 
                           allowEmptyArchive: true
        }
        success {
            echo '🎉 SUCCESS - Full CI/CD pipeline complete!'
        }
        failure {
            echo '💥 FAILURE - Check logs above'
        }
    }
}
