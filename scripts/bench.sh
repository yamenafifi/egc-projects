#!/usr/bin/env bash
# Serialised bench runner for the dev container.
#
# Several implementation agents share one bench and one site. Concurrent `bench migrate`
# (DDL + the patch log) or concurrent test runs corrupt each other, so every bench command
# goes through a mutex. Usage:
#
#   scripts/bench.sh --site dev.localhost migrate
#   scripts/bench.sh --site dev.localhost run-tests --app egc_projects --module egc_projects.tests.test_wbs
set -euo pipefail

CONTAINER=frappe_docker_devcontainer-frappe-1
LOCKDIR=/tmp/egc_projects_bench.lock
WAITED=0

while ! mkdir "$LOCKDIR" 2>/dev/null; do
	if [ "$WAITED" -ge 1800 ]; then
		echo "bench.sh: timed out waiting for $LOCKDIR (remove it if stale)" >&2
		exit 1
	fi
	sleep 3
	WAITED=$((WAITED + 3))
done
trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT

docker exec -w /workspace/development/frappe-bench "$CONTAINER" bench "$@"
