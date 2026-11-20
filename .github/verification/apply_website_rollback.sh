#!/usr/bin/env bash
# Fixed TEST-only target. The caller has already downloaded the encrypted backup.
set -euo pipefail
umask 077
DIR=/home/admin/website-rollback-20261121
cd /home/admin/custom_addons
test -s "$DIR/current-website-backup.tar.gz"
git rev-parse HEAD > "$DIR/backend-before-rollback-latest.txt"
# Refuse to replace any newer website customization, including local changes.
mapfile -t website_paths < <(git diff --name-only 90613ba c9f1d0d -- portal_api portal_content partner_management)
already_original=false
if git diff --quiet 90613ba -- "${website_paths[@]}"; then
  already_original=true
else
  git diff --quiet c9f1d0d -- "${website_paths[@]}"
fi
# Git must retain the original addon readability despite the private backup umask.
for path in "${website_paths[@]}"; do if [ -f "$path" ]; then chmod 644 -- "$path"; fi; done
outside=(. ':(exclude)portal_api/**' ':(exclude)portal_content/**' ':(exclude)partner_management/**' ':(exclude)**/__pycache__/**' ':(exclude)**/*.pyc')
before_local=$(git diff --binary -- "${outside[@]}" | sha256sum)
git fetch https://github.com/autochapeau/autochapeau-test_staging.git codex/website-test-rollback
ROLLBACK=$(git rev-parse FETCH_HEAD)
test "$(git show "$ROLLBACK:portal_api/__manifest__.py" | grep -c '17.0.1.0.31')" = 1
ODOO=$(sudo docker ps --filter name=autochapeau_staging_odoo_odoo --format '{{.ID}}' | head -1)
test -n "$ODOO"
test "$(sudo docker inspect "$ODOO" --format '{{index .Config.Labels "com.docker.swarm.service.name"}}')" = autochapeau_staging_odoo_odoo
sudo docker service inspect autochapeau_staging_website_web | python3 -c 'import json,sys; s=json.load(sys.stdin)[0]["Spec"]; assert s["Name"]=="autochapeau_staging_website_web"; assert "DB_NAME=autochapeau_prod_test" in s["TaskTemplate"]["ContainerSpec"]["Env"]; assert "Host(`web-test.autochapeau.com`)" in s["Labels"].values()'
if [ "$already_original" = false ]; then
sudo docker cp /tmp/website-original-sms.json "$ODOO:/tmp/website-original-sms.json"
sudo docker exec -u 0 "$ODOO" sh -c 'chown odoo:odoo /tmp/website-original-sms.json; chmod 600 /tmp/website-original-sms.json'
git show "$ROLLBACK:.github/verification/prepare_website_rollback.py" | sudo docker exec -i "$ODOO" python3 -
sudo docker exec -u 0 "$ODOO" rm -- /tmp/website-original-sms.json
git diff --binary c9f1d0d 90613ba -- portal_api portal_content partner_management > "$DIR/website-original.patch"
git apply --check "$DIR/website-original.patch"
git apply --index "$DIR/website-original.patch"
git -c user.name='TEST website rollback' -c user.email='test-rollback@autochapeau.invalid' commit -m 'Revert website integration on TEST preserving newer ERP source'
fi
for path in "${website_paths[@]}"; do if [ -f "$path" ]; then chmod 644 -- "$path"; fi; done
git show "$ROLLBACK:.github/verification/verify_website_rollback.py" > "$DIR/verify_website_rollback.py"
test "$before_local" = "$(git diff --binary -- "${outside[@]}" | sha256sum)"
echo UNRELATED_LOCAL_SOURCE_PRESERVED=true
sudo -n python3 .github/scripts/odoo_maintenance.py --service autochapeau_staging_odoo_odoo --database autochapeau_prod_test --modules portal_content,portal_api,partner_management --state-file "$DIR/maintenance-state.json"
ODOO=$(sudo docker ps --filter name=autochapeau_staging_odoo_odoo --format '{{.ID}}' | head -1)
test -n "$ODOO"
healthy=false
for attempt in $(seq 1 40); do
  if sudo docker exec "$ODOO" python3 -c "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8069/web/health',timeout=10).status==200"; then healthy=true; break; fi
  sleep 3
done
test "$healthy" = true
sudo docker exec -i "$ODOO" odoo shell -d autochapeau_prod_test --no-http --max-cron-threads=0 < "$DIR/verify_website_rollback.py"
# Retain the current server's unrelated smoke checks and adjust only the rolled-back module version.
python3 - <<'PY' | sudo docker exec -i "$ODOO" odoo shell -d autochapeau_prod_test --no-http --max-cron-threads=0
from pathlib import Path
s=Path('.github/verification/verify_staging.py').read_text()
print(s.replace('"partner_management": "17.0.1.6.5"','"partner_management": "17.0.1.6.4"'))
PY
sudo docker service update --image autochapeau-frontend:staging-b35136f --no-resolve-image autochapeau_staging_website_web
for attempt in $(seq 1 40); do
  IMAGE=$(sudo docker service ps autochapeau_staging_website_web --filter desired-state=running --format '{{.Image}}' | head -1)
  if [ "$IMAGE" = autochapeau-frontend:staging-b35136f ]; then break; fi
  sleep 3
done
curl --fail --silent --show-error --max-time 30 https://web-test.autochapeau.com/ > "$DIR/frontend-after.html"
curl --fail --silent --show-error --max-time 30 'https://web-test.autochapeau.com/v1/portal/statistics?db=autochapeau_prod_test&lang=en' > "$DIR/statistics-after.json"
python3 - "$DIR" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]);assert '<html' in (p/'frontend-after.html').read_text().lower();assert isinstance(json.loads((p/'statistics-after.json').read_text()),list)
PY
echo WEBSITE_TEST_ROLLBACK_COMPLETE=true
