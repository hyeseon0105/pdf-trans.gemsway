#!/bin/bash
# MySQL 초기화 스크립트
# Docker 컨테이너 시작 시 자동으로 스키마를 실행합니다.

echo "Waiting for MySQL to be ready..."
until mysql -h mysql -u root -p111111 -e "SELECT 1" > /dev/null 2>&1; do
  sleep 1
done

echo "MySQL is ready! Creating database and tables..."

mysql -h mysql -u root -p111111 <<EOF
CREATE DATABASE IF NOT EXISTS cadwell_translate CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE cadwell_translate;
SOURCE /docker-entrypoint-initdb.d/schema_mysql.sql;
EOF

echo "Database initialization complete!"



