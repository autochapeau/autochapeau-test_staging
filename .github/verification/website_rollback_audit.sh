#!/usr/bin/env bash
set -euo pipefail
umask 077
DIR=/home/admin/website-rollback-20261121
sudo install -d -m 700 -o "$(id -u)" -g "$(id -g)" "$DIR"
cd /home/admin/custom_addons
ODOO=$(sudo docker ps --filter name=autochapeau_staging_odoo_odoo --format '{{.ID}}' | head -1)
WEB=$(sudo docker ps --filter name=autochapeau_staging_website_web --format '{{.ID}}' | head -1)
test -n "$ODOO"; test -n "$WEB"
test "$(sudo docker inspect "$ODOO" --format '{{index .Config.Labels "com.docker.swarm.service.name"}}')" = autochapeau_staging_odoo_odoo
sudo docker service inspect autochapeau_staging_website_web > "$DIR/frontend-service-before.json"
sudo docker service inspect autochapeau_staging_odoo_odoo > "$DIR/odoo-service-before.json"
git rev-parse HEAD > "$DIR/backend-commit.txt"
git diff --binary -- . ':(exclude)**/__pycache__/**' ':(exclude)**/*.pyc' > "$DIR/server-local.patch"
tar --exclude='__pycache__' --exclude='*.pyc' -czf "$DIR/website-addons-before.tar.gz" portal_api portal_content partner_management
sudo docker cp "$WEB:/usr/share/nginx/html" "$DIR/frontend-build"
sudo chown -R "$(id -u):$(id -g)" "$DIR/frontend-build"
sudo docker image inspect autochapeau-frontend:staging-b35136f --format '{{.Id}}' > "$DIR/original-frontend-image.txt"
git fetch https://github.com/autochapeau/autochapeau-test_staging.git codex/website-test-rollback
AUDIT_COMMIT=$(git rev-parse FETCH_HEAD)
git show "$AUDIT_COMMIT:.github/verification/website_rollback_audit.py" | sudo docker exec -i "$ODOO" python3 -
sudo docker cp "$ODOO:/tmp/website-rollback-export/website-state.json" "$DIR/website-state.json"
sudo docker cp "$ODOO:/tmp/website-rollback-export/business-before.json" "$DIR/business-before.json"
sudo docker cp "$ODOO:/tmp/website-rollback-export/portal-tables.jsonl.gz" "$DIR/portal-tables.jsonl.gz"
sudo docker cp "$ODOO:/tmp/website-rollback-export/files" "$DIR/attachment-files"
sudo chown "$(id -u):$(id -g)" "$DIR/website-state.json" "$DIR/business-before.json"
tar -czf "$DIR/current-website-backup.tar.gz" -C "$DIR" frontend-service-before.json odoo-service-before.json backend-commit.txt server-local.patch website-addons-before.tar.gz frontend-build original-frontend-image.txt website-state.json business-before.json portal-tables.jsonl.gz attachment-files
echo WEBSITE_ROLLBACK_SERVER_BACKUP_READY=true
echo WEBSITE_ROLLBACK_BACKEND_COMMIT="$(cat "$DIR/backend-commit.txt")"
echo WEBSITE_ROLLBACK_ORIGINAL_FRONTEND_PRESENT=true
