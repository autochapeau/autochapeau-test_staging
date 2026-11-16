#!/usr/bin/env bash
# This release target deliberately has no production parameter.
set -euo pipefail
RELEASE_DIR="$1"
SERVICE=autochapeau_staging_website_web
cd "$RELEASE_DIR"
sudo docker service inspect "$SERVICE" > service-before.json
python3 - <<'PY'
import json
spec = json.load(open('service-before.json'))[0]['Spec']
assert spec['Name'] == 'autochapeau_staging_website_web'
labels = spec.get('Labels', {})
labels.update(spec['TaskTemplate']['ContainerSpec'].get('Labels', {}))
routes = [v.strip() for k,v in labels.items() if '.routers.' in k and k.endswith('.rule')]
assert routes == ['Host(`web-test.autochapeau.com`)'], routes
assert 'DB_NAME=autochapeau_prod_test' in spec['TaskTemplate']['ContainerSpec']['Env']
PY
OLD_IMAGE=$(sudo docker service inspect "$SERVICE" --format '{{.Spec.TaskTemplate.ContainerSpec.Image}}')
SOURCE=$(python3 -c 'import json; print(json.load(open("manifest.json"))["source_commit"])')
[[ "$SOURCE" =~ ^[a-f0-9]{40}$ ]]
sha256sum --check archive.sha256
python3 - <<'PY'
import pathlib, tarfile
root = pathlib.Path.cwd()
with tarfile.open('website.tar.gz') as archive:
    for item in archive.getmembers():
        target = (root / item.name).resolve()
        assert target.is_relative_to(root / 'build'), item.name
        assert item.isfile() or item.isdir(), item.name
    archive.extractall(root)
PY
test -f build/index.html
test -f build/assets/js/env.js
NEW_IMAGE="autochapeau-frontend:test-${SOURCE:0:12}"
printf 'FROM %s\nCOPY build/ /usr/share/nginx/html/\n' "$OLD_IMAGE" > Dockerfile
sudo docker build --pull=false --network=none -t "$NEW_IMAGE" .
rollback() {
  echo 'TEST website release failed; restoring the previous TEST image'
  sudo docker service update --image "$OLD_IMAGE" --no-resolve-image "$SERVICE"
}
trap rollback ERR
sudo docker service update --image "$NEW_IMAGE" --no-resolve-image "$SERVICE"
MATCHED=0
for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error --max-time 15 "https://web-test.autochapeau.com/release.json?release=$SOURCE" > live-release.json; then
    if python3 -c 'import json,sys; assert json.load(open("live-release.json"))["source_commit"] == sys.argv[1]' "$SOURCE"; then
      MATCHED=1
      break
    fi
  fi
  sleep 5
done
test "$MATCHED" = 1
curl --fail --silent --show-error --max-time 30 'https://web-test.autochapeau.com/v1/portal/statistics?lang=en' > statistics.json
python3 -c 'import json; data=json.load(open("statistics.json")); assert isinstance(data,list) and len(data)>0'
trap - ERR
echo "TEST_WEBSITE_RELEASE=$SOURCE"
