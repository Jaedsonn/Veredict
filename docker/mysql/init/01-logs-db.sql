-- Bancos com o charset do contrato; o `veriditi` já foi criado via MYSQL_DATABASE
-- Só roda com o volume vazio: depois de mudar, `docker compose down -v`
ALTER DATABASE `veriditi` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE DATABASE IF NOT EXISTS `veriditi_logs` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
