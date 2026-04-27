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
                
                echo "⏳ Waiting for MySQL to be ready..."
                for i in {1..12}; do
                    if docker exec mysql-db-dast mysqladmin ping -h localhost -u root -proot --silent; then
                        echo "✅ MySQL is ready!"
                        break
                    fi
                    echo "MySQL not ready yet... ($i/12)"
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
                echo "🔍 Running Bandit SAST scan..."
                bandit -r . -f json -o reports/bandit-report.json || true
                
                echo "🔍 Running Safety SCA scan..."
                safety check --full-report > reports/safety-report.txt || true
                
                echo "✅ Security scans completed"
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
                echo "🔨 Building ${FULL_IMAGE_TAG}..."
                docker build -t ${FULL_IMAGE_TAG} .
                docker tag ${FULL_IMAGE_TAG} ${DOCKERHUB_CREDENTIALS_USR}/${IMAGE_NAME}:latest
                
                echo "🔐 Logging into Docker Hub..."
                echo $DOCKERHUB_CREDENTIALS_PSW | docker login -u $DOCKERHUB_CREDENTIALS_USR --password-stdin
                
                echo "📤 Pushing with retries (3 attempts)..."
                for attempt in {1..3}; do
                    if timeout 900 docker push ${FULL_IMAGE_TAG}; then
                        echo "✅ Push successful on attempt $attempt!"
                        docker push ${DOCKERHUB_CREDENTIALS_USR}/${IMAGE_NAME}:latest || true
                        break
                    else
                        echo "❌ Push attempt $attempt failed. Retrying in 60s..."
                        sleep 60
                        if [ $attempt -eq 3 ]; then
                            echo "💥 All push attempts failed!"
                            exit 1
                        fi
                    fi
                done
                
                echo "FULL_IMAGE_TAG=${FULL_IMAGE_TAG}" > image_tag.env
                '''
            }
        }

        stage('Unit Tests with Test Database') {
            steps {
                sh '''
                . venv/bin/activate
                
                # Test with localhost (published port 3306)
                export DB_URI="mysql+pymysql://root:root@localhost:3306/imdb_db"
                
                echo "🧪 Running unit tests..."
                pytest tests/ -v --tb=short -o log_cli=true || true
                
                deactivate
                '''
            }
        }

        stage('Trivy Scan') {
            steps {
                sh '''
                source ./image_tag.env || echo "FULL_IMAGE_TAG=${FULL_IMAGE_TAG}"
                
                echo "🔍 Pulling Trivy scanner..."
                for attempt in {1..3}; do
                    if docker pull aquasec/trivy:0.56.0; then
                        echo "✅ Trivy pulled successfully!"
                        break
                    else
                        echo "❌ Trivy pull attempt $attempt failed, retrying..."
                        sleep 10
                    fi
                done
                
                echo "🔍 Running Trivy vulnerability scan..."
                docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
                    aquasec/trivy:0.56.0 image \
                    --format json \
                    --severity CRITICAL,HIGH \
                    --output reports/trivy-report.json \
                    --no-progress \
                    ${FULL_IMAGE_TAG} || true
                
                echo "📊 Trivy scan summary:"
                docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
                    aquasec/trivy:0.56.0 image \
                    --format table \
                    --severity CRITICAL,HIGH \
                    --no-progress \
                    ${FULL_IMAGE_TAG}
                '''
            }
        }

        stage('Run App & DAST') {
            when {
                expression { currentBuild.result == null || currentBuild.result == 'SUCCESS' }
            }
            steps {
                sh '''
                # Cleanup previous app container
                docker stop myapp6 || true
                docker rm myapp6 || true
                
                # Run the app
                echo "🚀 Starting application..."
                docker run -d --name myapp6 \
                    --network ${NETWORK_NAME} \
                    -p 5050:5050 \
                    -e DB_URI="${DB_URI_DOCKER}" \
                    ${FULL_IMAGE_TAG}
                
                echo "⏳ Waiting for app to be healthy..."
                for i in {1..20}; do
                    if curl -f http://localhost:5050/health || curl -f http://localhost:5050/ready; then
                        echo "✅ App is healthy!"
                        break
                    fi
                    echo "App not ready yet... ($i/20)"
                    sleep 3
                done
                
                # DAST with ZAP
                echo "🛡️ Running DAST with OWASP ZAP..."
                mkdir -p reports
                
                docker run --rm --network ${NETWORK_NAME} \
                    -v $(pwd)/reports:/zap/wrk/:rw \
                    -t ghcr.io/zaproxy/zaproxy:stable \
                    zap-baseline.py \
                    -t http://myapp6:5050 \
                    -r /zap/wrk/zap-report.html \
                    -J /zap/wrk/zap-report.json \
                    --hook-http-header "Host: localhost" \
                    -I || true
                
                echo "✅ DAST scan completed"
                '''
            }
        }
    }

    post {
        always {
            sh '''
            # Cleanup
            docker stop myapp6 mysql-db-dast || true
            docker rm myapp6 mysql-db-dast || true
            
            # Prune unused Docker objects
            docker image prune -f
            docker container prune -f
            '''
            
            // Archive comprehensive reports
            archiveArtifacts artifacts: 'reports/**, image_tag.env, zap-report.html', 
                           allowEmptyArchive: true, fingerprint: true
            
            // Publish HTML reports
            publishHTML([
                allowMissing: true,
                alwaysLinkToLastBuild: true,
                keepAll: true,
                reportDir: 'reports',
                reportFiles: 'zap-report.html',
                reportName: 'OWASP ZAP DAST Report'
            ])
        }
        
        success {
            echo '🎉 Pipeline completed successfully!'
            slackSend(channel: '#ci-cd', color: 'good', message: "✅ Pipeline SUCCESS: ${env.JOB_NAME} #${env.BUILD_NUMBER}")
        }
        
        failure {
            echo '💥 Pipeline failed!'
            slackSend(channel: '#ci-cd', color: 'danger', message: "❌ Pipeline FAILED: ${env.JOB_NAME} #${env.BUILD_NUMBER} (<${env.BUILD_URL}|View>)")
        }
    }
}
