"""Offline Odoo upgrade in a temporary Swarm service; restore app on failure.

Run as root on the deployment manager. Copy the exact application image, mounts,
environment, configs, secrets and networks without printing credentials.
"""
import argparse
import copy
import http.client
import json
import re
import signal
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import quote, urlencode

ACTIVE = {"new", "allocated", "pending", "assigned", "accepted", "preparing", "ready", "starting", "running"}


class DockerError(RuntimeError):
    def __init__(self, status, message):
        super().__init__("Docker HTTP %s: %s" % (status, message))
        self.status = status


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect("/var/run/docker.sock")


class Docker:
    def request(self, method, path, body=None):
        connection = UnixConnection("localhost", timeout=30)
        try:
            connection.request(method, path, json.dumps(body) if body is not None else None,
                               {"Content-Type": "application/json"})
            response = connection.getresponse()
            raw = response.read()
            value = json.loads(raw) if raw else {}
            if response.status >= 400:
                raise DockerError(response.status, value.get("message", "request failed"))
            return value
        finally:
            connection.close()

    def service(self, name):
        return self.request("GET", "/services/" + quote(name, safe=""))

    def tasks(self, service_id):
        return self.request("GET", "/tasks?" + urlencode({
            "filters": json.dumps({"service": [service_id]}),
        }))

    def task(self, task_id):
        try:
            return self.request("GET", "/tasks/" + quote(task_id, safe=""))
        except DockerError as error:
            if error.status != 404:
                raise
            return None

    def scale(self, name, replicas):
        # Swarm can advance a new service's version while scheduling its tasks.
        # Re-read the version on a conflict; never retry unrelated Docker errors.
        for attempt in range(6):
            service = self.service(name)
            spec = service["Spec"]
            if "Replicated" not in spec["Mode"]:
                raise RuntimeError("Only replicated services are supported")
            spec["Mode"]["Replicated"]["Replicas"] = replicas
            try:
                self.request("POST", "/services/%s/update?version=%s" % (
                    service["ID"], service["Version"]["Index"]), spec)
                return
            except DockerError as error:
                if attempt == 5 or "update out of sequence" not in str(error):
                    raise
                time.sleep(1)

    def remove(self, name):
        try:
            self.request("DELETE", "/services/" + quote(name, safe=""))
        except DockerError as error:
            if error.status != 404:
                raise


def wait_until(predicate, seconds, description):
    deadline = time.monotonic() + seconds
    while not predicate():
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out: " + description)
        time.sleep(2)


def migration_spec(service, database, modules, node_id, install_modules=""):
    template = copy.deepcopy(service["Spec"]["TaskTemplate"])
    container = template["ContainerSpec"]
    container["Command"] = ["odoo"]
    container["Args"] = ["-d", database]
    if modules:
        container["Args"] += ["-u", modules]
    if install_modules:
        container["Args"] += ["-i", install_modules]
    container["Args"] += ["--stop-after-init", "--no-http", "--max-cron-threads=0", "--workers=0"]
    container["Healthcheck"] = {"Test": ["NONE"]}
    container.pop("Labels", None)
    template["RestartPolicy"] = {"Condition": "none"}
    template.pop("ForceUpdate", None)
    template.setdefault("Placement", {}).setdefault("Constraints", []).append("node.id==" + node_id)
    for network in template.get("Networks", []):
        network.pop("Aliases", None)
    return {
        "Name": service["Spec"]["Name"] + "-migration",
        "Labels": {"com.autochapeau.migration-for": service["ID"]},
        "TaskTemplate": template,
        "Mode": {"Replicated": {"Replicas": 0}},
    }


def store_state(path, state):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def wait_stopped(docker, service_id):
    wait_until(lambda: not any(t["Status"]["State"] in ACTIVE for t in docker.tasks(service_id)),
               180, "stopping service " + service_id)


def remove_and_wait(docker, service_id):
    # Swarm's service filter returns 404 after service deletion. Capture task IDs
    # first, then inspect those tasks individually while shutdown completes.
    try:
        tasks = docker.tasks(service_id)
    except DockerError as error:
        if error.status != 404:
            raise
        tasks = []
    task_ids = [task["ID"] for task in tasks if task["Status"]["State"] in ACTIVE]
    docker.remove(service_id)
    def stopped():
        return not any(task and task["Status"]["State"] in ACTIVE
                       for task in (docker.task(task_id) for task_id in task_ids))
    wait_until(stopped, 180, "removing migration service")


def restore(docker, state, path):
    # Remove the updater and wait for its DB connections to close BEFORE restart.
    if state.get("migration_id"):
        remove_and_wait(docker, state["migration_id"])
    for key in ("backup_id", "check_id"):
        if state.get(key):
            remove_and_wait(docker, state[key])
    docker.scale(state["service_id"], state["replicas"])
    wait_until(lambda: sum(t["Status"]["State"] == "running" and
                          t.get("DesiredState") == "running"
                          for t in docker.tasks(state["service_id"])) >= state["replicas"],
               300, "restoring application replicas")
    path.unlink(missing_ok=True)
    print("Application replicas restored: %s" % state["replicas"], flush=True)


def run_migration(docker, migration_id, seconds=900):
    def finished():
        tasks = docker.tasks(migration_id)
        if not tasks:
            return False
        status = max(tasks, key=lambda t: t.get("CreatedAt", ""))["Status"]
        code = status.get("ContainerStatus", {}).get("ExitCode")
        if status["State"] == "complete" and code == 0:
            return True
        if status["State"] in {"failed", "rejected", "shutdown", "orphaned", "remove", "complete"}:
            raise RuntimeError("Migration task %s (exit %s): %s" % (
                status["State"], code, status.get("Err", "")))
        return False
    try:
        wait_until(finished, seconds, "Odoo maintenance task")
    finally:
        subprocess.run(["docker", "service", "logs", "--raw", "--tail", "100", migration_id],
                       check=False, timeout=30)


def deploy(docker, service_name, database, modules, state_path, install_modules="", release_check=False, verify_only=False):
    if verify_only and (database != 'autochapeau_prod_test' or not release_check):
        raise ValueError('Verification resume is restricted to the TEST release check')
    service = docker.service(service_name)
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["service_id"] != service["ID"] or state["replicas"] < 1:
            raise RuntimeError("Recovery state does not match the application service")
        print("Recovering interrupted maintenance", flush=True)
        restore(docker, state, state_path)
        service = docker.service(service_name)
    if not modules and not install_modules:
        print("No pending Odoo module changes", flush=True)
        return
    for names in (modules, install_modules):
        if names and not re.fullmatch(r"[A-Za-z0-9_]+(?:,[A-Za-z0-9_]+)*", names):
            raise ValueError("Invalid module names")
    mode = service["Spec"]["Mode"]
    if "Replicated" not in mode or mode["Replicated"].get("Replicas", 0) < 1:
        raise RuntimeError("Application must be a running replicated service")
    node_id = docker.request("GET", "/info")["Swarm"]["NodeID"]
    if not any(t.get("NodeID") == node_id and t["Status"]["State"] == "running"
               for t in docker.tasks(service["ID"])):
        raise RuntimeError("Application must run on the deployment host (code bind mount)")
    spec = migration_spec(service, database, modules, node_id, install_modules)
    try:
        previous = docker.service(spec["Name"])
    except DockerError as error:
        if error.status != 404:
            raise
    else:
        if previous["Spec"].get("Labels", {}).get("com.autochapeau.migration-for") != service["ID"]:
            raise RuntimeError("Migration service name belongs to another service")
        remove_and_wait(docker, previous["ID"])
    state = {"service_id": service["ID"], "replicas": mode["Replicated"]["Replicas"]}
    state["migration_id"] = docker.request("POST", "/services/create", spec)["ID"]
    store_state(state_path, state)
    try:
        print("Entering maintenance; " + ("verifying existing upgrade" if verify_only else "upgrading: " + modules), flush=True)
        if install_modules:
            print("Installing modules: " + install_modules, flush=True)
        docker.scale(service["ID"], 0)
        wait_stopped(docker, service["ID"])
        if release_check:
            smoke = Path(__file__).parent.parent / "verification" / "verify_staging.py"
            smoke_source = smoke.read_text(encoding="utf-8")
            mobile_tests = smoke.with_name("run_mobile_unique_tests.py")
            if mobile_tests.exists():
                smoke_source += "\n" + mobile_tests.read_text(encoding="utf-8")
            if database == 'autochapeau_prod_test' and not verify_only:
                smoke_source += '\n' + smoke.with_name('commission_period_release_checks.py').read_text(encoding='utf-8')
            material_tests = smoke.with_name("run_service_material_tests.py")
            if material_tests.exists() and "workorder_service_components" in modules.split(","):
                smoke_source += "\n" + material_tests.read_text(encoding="utf-8")
            maintenance_tests = smoke.with_name("run_maintenance_tests.py")
            if maintenance_tests.exists() and "order_maintenance" in modules.split(","):
                smoke_source += "\n" + maintenance_tests.read_text(encoding="utf-8")
            code = "SMOKE_SOURCE = " + repr(smoke_source) + "\n" + Path(__file__).with_name("production_release_check.py").read_text(encoding="utf-8")
            for mode_name, key in (() if verify_only else (("backup", "backup_id"),)):
                task_spec = copy.deepcopy(spec)
                task_spec["Name"] = service["Spec"]["Name"] + "-release-" + mode_name
                task_spec["TaskTemplate"]["ContainerSpec"].update(Command=["python3"], Args=["-c", code, database, mode_name])
                state[key] = docker.request("POST", "/services/create", task_spec)["ID"]
                store_state(state_path, state)
                docker.scale(state[key], 1)
                run_migration(docker, state[key], seconds=1500)
        if not verify_only:
            docker.scale(state["migration_id"], 1)
            run_migration(docker, state["migration_id"])
        if release_check:
            task_spec = copy.deepcopy(spec)
            task_spec["Name"] = service["Spec"]["Name"] + "-release-verify"
            task_spec["TaskTemplate"]["ContainerSpec"].update(Command=["python3"], Args=["-c", code, database, "verify"])
            state["check_id"] = docker.request("POST", "/services/create", task_spec)["ID"]
            store_state(state_path, state)
            docker.scale(state["check_id"], 1)
            run_migration(docker, state["check_id"], seconds=1800 if database == 'autochapeau_prod_test' else 900)
        state["upgrade_complete"] = True
        store_state(state_path, state)
    finally:
        restore(docker, state, state_path)


def interrupted(number, frame):
    raise RuntimeError("Deployment interrupted by signal %s" % number)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--modules", default="")
    parser.add_argument("--install-modules", default="")
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--release-check", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, interrupted)
    deploy(Docker(), args.service, args.database, args.modules, args.state_file, args.install_modules, args.release_check, args.verify_only)
