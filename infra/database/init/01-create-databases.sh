#!/bin/bash
# Creates one database + one login role per service (init.md §2.4). DEVELOPMENT ONLY.
set -euo pipefail
create() {
  local db=$1 role=$2 pw=$3
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-SQL
    CREATE ROLE ${role} LOGIN PASSWORD '${pw}';
    CREATE DATABASE ${db} OWNER ${role};
    REVOKE CONNECT ON DATABASE ${db} FROM PUBLIC;
    GRANT CONNECT ON DATABASE ${db} TO ${role};
SQL
}
create employer_db employer_app "${EMPLOYER_DB_PASSWORD}"
create member_db member_app "${MEMBER_DB_PASSWORD}"
create contribution_db contribution_app "${CONTRIBUTION_DB_PASSWORD}"
create claim_db claim_app "${CLAIM_DB_PASSWORD}"
create payment_simulator_db payment_simulator_app "${PAYMENT_SIMULATOR_DB_PASSWORD}"
create workflow_db workflow_app "${WORKFLOW_DB_PASSWORD}"
create grievance_db grievance_app "${GRIEVANCE_DB_PASSWORD}"
create audit_db audit_app "${AUDIT_DB_PASSWORD}"
create reporting_db reporting_app "${REPORTING_DB_PASSWORD}"
create intelligence_db intelligence_app "${INTELLIGENCE_DB_PASSWORD}"
create pension_db pension_app "${PENSION_DB_PASSWORD}"
create platform_db platform_app "${PLATFORM_DB_PASSWORD}"
create mock_integrations_db mock_integrations_app "${MOCK_INTEGRATIONS_DB_PASSWORD}"
create keycloak_db keycloak_app "${KEYCLOAK_DB_PASSWORD}"
create compliance_db compliance_app "${COMPLIANCE_DB_PASSWORD}"
# Read-only role for reporting projections.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname reporting_db <<-SQL
  CREATE ROLE reporting_ro LOGIN PASSWORD '${REPORTING_RO_DB_PASSWORD}';
  GRANT CONNECT ON DATABASE reporting_db TO reporting_ro;
  GRANT USAGE ON SCHEMA public TO reporting_ro;
  ALTER DEFAULT PRIVILEGES FOR ROLE reporting_app IN SCHEMA public GRANT SELECT ON TABLES TO reporting_ro;
SQL
