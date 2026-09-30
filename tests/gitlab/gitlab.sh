#!/usr/bin/env bash
# Local GitLab CE for testing sphinx-redline's GitLab support, in podman.
#
# Usage: tests/gitlab/gitlab.sh up|down|status
#
#   up      start GitLab (first start takes several minutes), then provision a
#           reviewer user, a comments project with a `redline` branch, a
#           project access token (guest mode) and an OAuth application
#           ("Sign in with GitLab"). Settings go to .gitlab-test.env, which
#           tests/test_gitlab.py reads.
#   down    remove the container, its volumes and .gitlab-test.env.
#   status  show whether the container runs and GitLab answers.
#
# Everything is local and throwaway: the container listens on localhost only.
set -euo pipefail

VERSION="${REDLINE_GITLAB_VERSION:-19.4.1-ce.0}"
NAME="redline-gitlab"
PORT="${REDLINE_GITLAB_PORT:-8929}"
SITE_PORT="${REDLINE_GITLAB_SITE_PORT:-8765}"
URL="http://localhost:${PORT}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ROOT}/.gitlab-test.env"
PROJECT="docs-comments"

info() { echo " - $*"; }
fail() { echo " - ERROR: $*" >&2; exit 1; }

json() {  # json <python expression on `d`>  < json
  python3 -c "import json, sys; d = json.load(sys.stdin); print($1)"
}

api() {  # api <method> <path> [curl args...]
  local method="$1" path="$2"
  shift 2
  curl -sS --fail-with-body -X "${method}" -H "PRIVATE-TOKEN: ${ROOT_TOKEN}" "$@" "${URL}/api/v4${path}"
}

running() {
  [[ "$(podman inspect -f '{{.State.Running}}' "${NAME}" 2>/dev/null)" == "true" ]]
}

ready() {
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "${URL}/users/sign_in")" == "200" ]]
}

start() {
  if running; then
    info "container ${NAME} already running"
    return
  fi
  if podman container exists "${NAME}"; then
    podman start "${NAME}" >/dev/null
    return
  fi
  ROOT_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18) + "Aa1!")')"
  info "starting GitLab ${VERSION} on ${URL}"
  podman run -d --name "${NAME}" \
    --hostname localhost \
    -p "127.0.0.1:${PORT}:${PORT}" \
    --shm-size 256m \
    -v redline-gitlab-config:/etc/gitlab \
    -v redline-gitlab-logs:/var/log/gitlab \
    -v redline-gitlab-data:/var/opt/gitlab \
    -e GITLAB_OMNIBUS_CONFIG="
      external_url '${URL}'
      gitlab_rails['initial_root_password'] = '${ROOT_PASSWORD}'
      gitlab_rails['usage_ping_enabled'] = false
      puma['worker_processes'] = 0
      sidekiq['concurrency'] = 5
      prometheus_monitoring['enable'] = false
      gitlab_kas['enable'] = false
    " \
    "docker.io/gitlab/gitlab-ce:${VERSION}" >/dev/null
  echo "ROOT_PASSWORD=${ROOT_PASSWORD}" >"${ENV_FILE}.partial"
}

wait_ready() {
  info "waiting for GitLab to answer (first start: several minutes)"
  for _ in $(seq 1 180); do
    if ready; then
      info "GitLab is up"
      return
    fi
    running || fail "container stopped; see: podman logs ${NAME}"
    sleep 5
  done
  fail "GitLab did not come up within 15 minutes"
}

rails() {
  podman exec "${NAME}" gitlab-rails runner "$1"
}

provision() {
  if [[ -f "${ENV_FILE}" ]]; then
    info "already provisioned (${ENV_FILE})"
    return
  fi
  info "creating an admin token"
  ROOT_TOKEN="$(rails "
    user = User.find_by_username('root')
    token = user.personal_access_tokens.create!(
      name: 'redline-setup', scopes: ['api', 'sudo'], expires_at: 300.days.from_now)
    puts token.token
  " | tail -1)"
  [[ -n "${ROOT_TOKEN}" ]] || fail "could not create the admin token"

  local password project_id project_token client_id
  password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18) + "Aa1!")')"

  info "creating user 'reviewer'"
  api POST /users \
    --data-urlencode "username=reviewer" --data-urlencode "name=Reviewer" \
    --data-urlencode "email=reviewer@example.org" --data-urlencode "password=${password}" \
    --data-urlencode "skip_confirmation=true" >/dev/null
  # Admin-set passwords must normally be changed at first sign-in.
  rails "User.find_by_username('reviewer').update!(password_expires_at: nil)" >/dev/null

  info "creating project root/${PROJECT} with a 'redline' branch"
  project_id="$(api POST /projects --data-urlencode "name=${PROJECT}" \
    --data-urlencode "initialize_with_readme=true" --data-urlencode "visibility=public" | json 'd["id"]')"
  api POST "/projects/${project_id}/repository/branches" \
    --data-urlencode "branch=redline" --data-urlencode "ref=main" >/dev/null
  api POST "/projects/${project_id}/members" \
    --data-urlencode "username=reviewer" --data-urlencode "access_level=30" >/dev/null

  info "creating a Developer project access token (guest mode)"
  project_token="$(api POST "/projects/${project_id}/access_tokens" \
    -H "Content-Type: application/json" \
    --data "{\"name\": \"redline-guest\", \"scopes\": [\"api\"], \"access_level\": 30,
             \"expires_at\": \"$(date -d '+300 days' +%F)\"}" | json 'd["token"]')"

  info "creating a public OAuth application (Sign in with GitLab)"
  client_id="$(api POST /applications \
    --data-urlencode "name=sphinx-redline test" \
    --data-urlencode "redirect_uri=http://127.0.0.1:${SITE_PORT}/" \
    --data-urlencode "scopes=api" --data-urlencode "confidential=false" | json 'd["application_id"]')"

  {
    cat "${ENV_FILE}.partial" 2>/dev/null || true
    echo "REDLINE_GITLAB_URL=${URL}"
    echo "REDLINE_GITLAB_ROOT_TOKEN=${ROOT_TOKEN}"
    echo "REDLINE_GITLAB_PROJECT=root/${PROJECT}"
    echo "REDLINE_GITLAB_PROJECT_TOKEN=${project_token}"
    echo "REDLINE_GITLAB_CLIENT_ID=${client_id}"
    echo "REDLINE_GITLAB_USER=reviewer"
    echo "REDLINE_GITLAB_PASSWORD=${password}"
    echo "REDLINE_GITLAB_SITE_PORT=${SITE_PORT}"
  } >"${ENV_FILE}"
  rm -f "${ENV_FILE}.partial"
  info "provisioned; settings in ${ENV_FILE}"
}

case "${1:-}" in
  up)
    command -v podman >/dev/null || fail "podman is not installed"
    start
    wait_ready
    provision
    ;;
  down)
    podman rm -f "${NAME}" >/dev/null 2>&1 || true
    podman volume rm -f redline-gitlab-config redline-gitlab-logs redline-gitlab-data >/dev/null 2>&1 || true
    rm -f "${ENV_FILE}" "${ENV_FILE}.partial"
    info "removed ${NAME}, its volumes and ${ENV_FILE}"
    ;;
  status)
    if running; then info "container running"; else info "container not running"; fi
    if ready; then info "GitLab answers on ${URL}"; else info "GitLab does not answer on ${URL}"; fi
    ;;
  *)
    echo "usage: $0 up|down|status" >&2
    exit 2
    ;;
esac
