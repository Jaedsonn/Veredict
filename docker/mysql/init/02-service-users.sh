# Usuários MySQL do Veriditi: `migrator` (DDL) e um usuário de runtime por serviço
#
# Não é executável de propósito: o entrypoint do mysql faz `source` e expõe o
# docker_process_sql. Em `.sql` as senhas não sairiam do ambiente (sem expansão de ${VAR})
# GRANT de tabela fica na migration que cria a tabela: aqui elas ainda não existem
#
# Para reaplicar num volume existente (ex.: senha trocada no .env):
#   docker compose exec mysql bash /docker-entrypoint-initdb.d/02-service-users.sh

if ! command -v docker_process_sql >/dev/null 2>&1; then
  docker_process_sql() { mysql --protocol=socket -uroot -p"${MYSQL_ROOT_PASSWORD}" "$@"; }
fi

for _veriditi_var in DB_MIGRATOR_PASSWORD AUTH_DB_PASSWORD NOTIFICATION_DB_PASSWORD LOGS_DB_PASSWORD; do
  if [ -z "${!_veriditi_var:-}" ]; then
    echo "02-service-users.sh: defina ${_veriditi_var}" >&2
    exit 1
  fi
  # A senha entra num literal SQL entre aspas simples
  case "${!_veriditi_var}" in
    *\'* | *\\*)
      echo "02-service-users.sh: ${_veriditi_var} não pode ter aspas simples nem barra invertida" >&2
      exit 1
      ;;
  esac
done
unset _veriditi_var

# CREATE ... IF NOT EXISTS não troca senha; o ALTER USER deixa o script reaplicável
docker_process_sql <<SQL
CREATE USER IF NOT EXISTS 'migrator'@'%' IDENTIFIED BY '${DB_MIGRATOR_PASSWORD}';
ALTER USER 'migrator'@'%' IDENTIFIED BY '${DB_MIGRATOR_PASSWORD}';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES
  ON \`veriditi\`.* TO 'migrator'@'%' WITH GRANT OPTION;
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES
  ON \`veriditi_logs\`.* TO 'migrator'@'%' WITH GRANT OPTION;

CREATE USER IF NOT EXISTS 'auth_svc'@'%' IDENTIFIED BY '${AUTH_DB_PASSWORD}';
ALTER USER 'auth_svc'@'%' IDENTIFIED BY '${AUTH_DB_PASSWORD}';

CREATE USER IF NOT EXISTS 'notification_svc'@'%' IDENTIFIED BY '${NOTIFICATION_DB_PASSWORD}';
ALTER USER 'notification_svc'@'%' IDENTIFIED BY '${NOTIFICATION_DB_PASSWORD}';

CREATE USER IF NOT EXISTS 'veriditi_logs_writer'@'%' IDENTIFIED BY '${LOGS_DB_PASSWORD}';
ALTER USER 'veriditi_logs_writer'@'%' IDENTIFIED BY '${LOGS_DB_PASSWORD}';
SQL
