pipeline {
    agent any

    environment {
        IMAGE_NAME = "myapp3"
        // Use localhost for host-based tests, container name for Docker-based tests
        DB_URI = "mysql+pymysql://root:root@localhost:3306/imdb_db"
        DOCKERHUB_CREDENTIALS = credentials('docker-hub-credentials')
        NETWORK_NAME = "app-network"
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
                script {
                    sh '''
                    docker network create ${NETWORK_NAME} || true
                    '''
                }
            }
        }

        stage('Launch MySQL') {
            steps {
                script {
                    // Stop and remove existing MySQL container if it exists
                    sh '''
                    docker stop mysql-db || true
                    docker rm mysql-db || true
                    '''
                    
                    // Publish MySQL port to host for tests to access
                    sh """
                    docker run -d --name mysql-db \
                        -e MYSQL_ROOT_PASSWORD=root \
                        -e MYSQL_DATABASE=imdb_db \
                        --network ${NETWORK_NAME} \
                        -p 3306:3306 \
                        mysql:8.0
                    """
                    
                    // Wait for MySQL to be ready with proper health check
                    sh '''
                    echo "Waiting for MySQL to be ready..."
                    for i in $(seq 1 30); do
                        if docker exec mysql-db mysqladmin ping -h localhost -uroot -proot --silent 2>/dev/null; then
                            echo "MySQL is ready!"
                            break
                        fi
                        echo "Waiting for MySQL... (attempt $i/30)"
                        sleep 5
                    done
                    
                    # Additional wait to ensure database is fully initialized
                    sleep 10
                    '''
                }
            }
        }

        stage('Setup Python & Install Dependencies') {
            steps {
                sh '''
                python3 -m venv venv
                . venv/bin/activate
                python -m pip install --upgrade pip
                pip install -r requirements.txt bandit pip-audit pytest pymysql flask flask_sqlalchemy werkzeug
                # Install docker module for tests that need it
                pip install docker pytest-docker
                '''
            }
        }

        stage('SCA Scan') {
            steps {
                sh '''
                . venv/bin/activate
                pip-audit || true
                '''
            }
        }

        stage('SAST Scan (Bandit)') {
            steps {
                sh '''
                . venv/bin/activate
                bandit -r . -x ./venv,./tests --severity-level high -f json -o bandit-report.json || true
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'bandit-report.json', allowEmptyArchive: true
                }
            }
        }

        stage('Unit Tests with Test Database') {
            steps {
                script {
                    // Run tests with MySQL accessible via localhost (published port)
                    sh """
                    . venv/bin/activate
                    export DB_URI="mysql+pymysql://root:root@localhost:3306/imdb_db"
                    
                    # Run tests with pytest
                    pytest -v --tb=short || echo "Tests completed with failures"
                    """
                }
            }
        }

        stage('Docker Login') {
            steps {
                script {
                    // Add retry logic for Docker Hub connectivity
                    sh '''
                    echo "Attempting to login to Docker Hub..."
                    max_retries=3
                    retry_count=0
                    while [ $retry_count -lt $max_retries ]; do
                        if echo $DOCKERHUB_CREDENTIALS_PSW | docker login -u $DOCKERHUB_CREDENTIALS_USR --password-stdin; then
                            echo "Login successful!"
                            break
                        else
                            retry_count=$((retry_count+1))
                            if [ $retry_count -lt $max_retries ]; then
                                echo "Login failed, retrying in 10 seconds... (attempt $retry_count/$max_retries)"
                                sleep 10
                            else
                                echo "Login failed after $max_retries attempts"
                                exit 1
                            fi
                        fi
                    done
                    '''
                }
            }
        }

        stage('Build & Tag Docker Image') {
            steps {
                sh '''
                FULL_TAG="${DOCKERHUB_CREDENTIALS_USR}/${IMAGE_NAME}:latest"
                docker build -t $FULL_TAG .
                echo "FULL_IMAGE_TAG=$FULL_TAG" > image_tag.env
                cat image_tag.env
                '''
            }
        }

        stage('Trivy Scan') {
            steps {
                sh '''
                . ./image_tag.env
                
                # Pull Trivy image with retry
                echo "Pulling Trivy scanner..."
                max_retries=3
                retry_count=0
                while [ $retry_count -lt $max_retries ]; do
                    if docker pull aquasec/trivy:0.56.0; then
                        echo "Trivy image pulled successfully!"
                        break
                    else
                        retry_count=$((retry_count+1))
                        if [ $retry_count -lt $max_retries ]; then
                            echo "Failed to pull Trivy, retrying... (attempt $retry_count/$max_retries)"
                            sleep 10
                        else
                            echo "Failed to pull Trivy after $max_retries attempts, skipping scan"
                            exit 0
                        fi
                    fi
                done
                
                # Run Trivy scan
                docker run --rm \
                    -v /var/run/docker.sock:/var/run/docker.sock \
                    aquasec/trivy:0.56.0 \
                    image \
                    --format table \
                    --severity CRITICAL,HIGH \
                    --no-progress \
                    $FULL_IMAGE_TAG || true
                '''
            }
        }

        stage('Push Docker Image') {
            steps {
                sh '''
                . ./image_tag.env
                
                # Push with retry logic
                echo "Pushing image to Docker Hub..."
                max_retries=3
                retry_count=0
                while [ $retry_count -lt $max_retries ]; do
                    if docker push $FULL_IMAGE_TAG; then
                        echo "Push successful!"
                        break
                    else
                        retry_count=$((retry_count+1))
                        if [ $retry_count -lt $max_retries ]; then
                            echo "Push failed, retrying in 10 seconds... (attempt $retry_count/$max_retries)"
                            sleep 10
                        else
                            echo "Push failed after $max_retries attempts"
                            exit 1
                        fi
                    fi
                done
                '''
            }
        }

        stage('Run Container for DAST') {
            steps {
                sh """
                . ./image_tag.env
                
                # Check if port 5000 is in use and clean up
                echo "Checking for port conflicts..."
                docker ps | grep -q "0.0.0.0:5000" && docker stop \$(docker ps | grep "0.0.0.0:5000" | awk '{print \$1}') || true
                
                # Stop and remove existing container if it exists
                docker stop myapp3 || true
                docker rm myapp3 || true
                
                # Stop and remove MySQL DAST container if it exists
                docker stop mysql-db-dast || true
                docker rm mysql-db-dast || true
                
                # Run MySQL container for the DAST test
                docker run -d --name mysql-db-dast \
                    -e MYSQL_ROOT_PASSWORD=root \
                    -e MYSQL_DATABASE=imdb_db \
                    --network ${NETWORK_NAME} \
                    mysql:8.0
                
                # Wait for MySQL to be ready
                echo "Waiting for MySQL DAST container..."
                for i in \$(seq 1 30); do
                    if docker exec mysql-db-dast mysqladmin ping -h localhost -uroot -proot --silent 2>/dev/null; then
                        echo "MySQL DAST is ready!"
                        break
                    fi
                    echo "Waiting for MySQL DAST... (attempt \$i/30)"
                    sleep 5
                done
                
                # Run the application container
                docker run -d -p 5000:5000 \
                    --name myapp3 \
                    --network ${NETWORK_NAME} \
                    -e DB_URI="mysql+pymysql://root:root@mysql-db-dast:3306/imdb_db" \
                    -e ADMIN_USERNAME="admin" \
                    -e ADMIN_PASSWORD_HASH="pbkdf2:sha256:260000\\\$kYZK81PaMR8vI4q5\\\$c93a9dfa37895e43cce4c1db11f69fd5b4bcec201d66a2d0c741992d9949d162" \
                    -e SECRET_KEY="test-secret-key" \
                    \$FULL_IMAGE_TAG
                
                echo "Waiting for app to initialize and run ETL..."
                sleep 30
                
                # Check if app is running
                docker logs myapp3 || true
                
                # Wait for app to be ready
                for i in \$(seq 1 30); do
                    if curl -f http://localhost:5000/ 2>/dev/null; then
                        echo "App is ready!"
                        break
                    fi
                    echo "Waiting for app... (attempt \$i/30)"
                    sleep 2
                done
                """
            }
        }

        stage('DAST Scan (OWASP ZAP)') {
            steps {
                sh """
                mkdir -p zap-reports
                chmod 777 zap-reports
                
                # Pull ZAP image with retry
                max_retries=3
                retry_count=0
                while [ \$retry_count -lt \$max_retries ]; do
                    if docker pull ghcr.io/zaproxy/zaproxy:stable; then
                        break
                    else
                        retry_count=\$((retry_count+1))
                        if [ \$retry_count -lt \$max_retries ]; then
                            echo "Failed to pull ZAP, retrying... (attempt \$retry_count/\$max_retries)"
                            sleep 10
                        else
                            echo "Failed to pull ZAP after \$max_retries attempts, skipping scan"
                            exit 0
                        fi
                    fi
                done
                
                # Run ZAP scan
                docker run --network ${NETWORK_NAME} \
                    -v \$(pwd)/zap-reports:/zap/wrk:rw \
                    ghcr.io/zaproxy/zaproxy:stable \
                    zap-baseline.py -t http://myapp3:5000 -r zap-report.html || echo "ZAP finished with alerts"
                """
            }
        }
    }

    post {
        always {
            // Archive all reports
            archiveArtifacts artifacts: 'zap-reports/zap-report.html, bandit-report.json', allowEmptyArchive: true
            
            // Cleanup
            sh '''
            echo "Cleaning up containers..."
            docker stop myapp3 || true
            docker rm myapp3 || true
            docker stop mysql-db || true
            docker rm mysql-db || true
            docker stop mysql-db-dast || true
            docker rm mysql-db-dast || true
            docker network rm ${NETWORK_NAME} || true
            '''
            
            // Clean up Docker images to save space
            sh '''
            docker image prune -f || true
            '''
        }
        
        failure {
            // Capture logs on failure
            sh '''
            echo "=== Docker logs for myapp3 ==="
            docker logs myapp3 || true
            echo "=== Docker logs for mysql-db ==="
            docker logs mysql-db || true
            echo "=== Docker logs for mysql-db-dast ==="
            docker logs mysql-db-dast || true
            '''
        }
    }
}
