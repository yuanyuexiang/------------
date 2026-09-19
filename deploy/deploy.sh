#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Each release contains compose.prod.yml, release.env and this script.
release=$(cd "${1:?Usage: deploy.sh RELEASE_DIRECTORY}" && pwd)
root=$(dirname "$(dirname "$release")")
test -s "$root/.env"
test -s "$release/release.env"
exec 9>"$root/deploy.lock"
flock -n 9 || { echo 'Another deployment is running' >&2; exit 1; }
docker network inspect matrix-network >/dev/null
previous=$(readlink -f "$root/current" || true)
phase=prepare
step=prepare

compose() {
  docker compose --project-name jinbang --env-file "$root/.env" \
    --env-file "$release/release.env" -f "$release/compose.prod.yml" "$@"
}

failed() {
  local status=$?
  trap - ERR
  echo "Deployment failed during $phase (step=$step, exit=$status)" >&2
  # Diagnose host-wide stalls without printing environment variables or credentials.
  free -m >&2 || true
  for pressure in /proc/pressure/memory /proc/pressure/io; do
    if [[ -r "$pressure" ]]; then
      echo "$pressure" >&2
      cat "$pressure" >&2 || true
    fi
  done
  # Capture health failures before rollback/stop changes the container state.
  compose ps -a || true
  local container
  for container in $(compose ps -aq); do
    docker inspect --format '{{.Name}} state={{.State.Status}} oom={{.State.OOMKilled}} health={{json .State.Health}}' \
      "$container" || true
  done
  if [[ "$phase" == app && -n "$previous" && -f "$previous/release.env" ]]; then
    echo 'Restoring previous application images; database migrations are NOT reverted.' >&2
    docker compose --project-name jinbang --env-file "$root/.env" \
      --env-file "$previous/release.env" -f "$previous/compose.prod.yml" \
      up -d --no-build --pull never --wait --wait-timeout 180 || \
      echo 'Application rollback failed; manual recovery required.' >&2
  elif [[ "$phase" == migration ]]; then
    echo 'Application remains stopped. Inspect migration and database backup before recovery.' >&2
  elif [[ "$phase" == app ]]; then
    compose stop jb-web jb-worker jb-api || true
    echo 'First release failed; application stopped.' >&2
  fi
  exit "$status"
}
trap failed ERR

compose config --quiet
# All images must be available before stopping a running application.
compose pull
compose up -d --wait --wait-timeout 120 db redis
mkdir -p "$root/backups"
compose stop jb-worker jb-api
phase=migration
compose exec -T db pg_dump -U jinbang -d jinbang -Fc > "$root/backups/$(basename "$release").dump"
compose run --rm --no-deps jb-api alembic -c deploy/alembic.ini upgrade head
phase=app
step=container-startup
compose up -d --no-build --pull never --wait --wait-timeout 360
domain=$(sed -n 's/^DEPLOY_DOMAIN=//p' "$root/.env")
domain=${domain:-jinbang.matrix-net.tech}
check_https() {
  local url=$1
  echo "Checking $step: $url"
  # Both endpoints can see transient TLS/network failures during first issuance.
  # Keep certificate verification enabled and bound the retry budget.
  curl --fail --silent --show-error --retry 24 --retry-all-errors --retry-delay 10 \
    --retry-max-time 300 --connect-timeout 5 --max-time 15 --output /dev/null "$url"
  echo "Passed $step"
}
step=https-api
check_https "https://$domain/api/health"
step=https-homepage
check_https "https://$domain/"
step=activate-release
if [[ -n "$previous" && -d "$previous" ]]; then
  ln -sfn "$previous" "$root/previous"
fi
ln -sfn "$release" "$root/current"
echo "Deployment healthy: $(basename "$release")"
