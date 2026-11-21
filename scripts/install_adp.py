"""Install ADP from an operator-selected local Git archive. Python 3.11+."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from dataclasses import dataclass


NAME = "adp-codex"
MANAGED = Path(".local/share/adp-codex-install")
HEX = re.compile(r"[0-9a-f]{64}")
SHA = re.compile(r"[0-9a-f]{40}")
GENERATION = re.compile(r"adp-managed-[0-9a-f]{32}")
VERSION = re.compile(r"[0-9]+(?:\.[0-9]+)+")
SKILL = "skills/adp-codex/SKILL.md"
CATALOG_PLUGIN = "plugins/adp-codex"
MAX_SOURCE = 16 * 1024 * 1024
MAX_RESPONSE = 4 * 1024 * 1024
ENGINE_ENTRYPOINT = {"adp/__init__.py", "adp/__main__.py", "adp/cli.py"}
LAUNCHER_ALIAS = Path("engine/bin/adp")
LAUNCHER_LINK = "../../bin/adp"


class Refusal(Exception):
    pass


class UnknownCodexState(Refusal):
    pass


def require(condition: object, message: str) -> None:
    if not condition:
        raise Refusal(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def engine_file(name: str) -> bool:
    return re.fullmatch(r"adp/[a-zA-Z0-9_]+\.py", name) is not None


def plugin_file(name: str) -> bool:
    return name in {"plugin.json", SKILL} or re.fullmatch(r"docs/[a-zA-Z0-9_/-]+\.(?:md|json)", name) is not None


def marketplace_payload(name: str) -> dict:
    return {"name": name, "plugins": [{
        "name": NAME, "source": {"source": "local", "path": "./" + CATALOG_PLUGIN},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Productivity"}]}


def launcher_script(engine: Path) -> str:
    interpreter = shlex.quote(str(engine / "bin/python"))
    return f'#!/bin/sh\nexec {interpreter} -I -B -m adp "$@"\n'


def write_launcher(generation: Path) -> None:
    launcher = generation / "bin/adp"
    launcher.parent.mkdir()
    launcher.write_text(launcher_script(generation / "venv"))
    launcher.chmod(0o700)
    # Earlier installer drafts and archived skills used this stable path.
    alias = generation / LAUNCHER_ALIAS
    alias.parent.mkdir(parents=True)
    alias.symlink_to(LAUNCHER_LINK)


@dataclass(frozen=True)
class Source:
    files: dict[str, bytes]
    receipt: dict

    @classmethod
    def read(cls, path: Path, revision: str, expected: str) -> Source:
        require(SHA.fullmatch(revision) and HEX.fullmatch(expected),
                "Supply a full lowercase Git commit SHA and SHA-256 digest.")
        try:
            with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK), "rb") as stream:
                require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Select a regular archive file.")
                data = stream.read(MAX_SOURCE + 1)
        except OSError:
            raise Refusal("Cannot read the local archive. Obtain the selected ADP archive and retry.") from None
        require(len(data) <= MAX_SOURCE and digest(data) == expected,
                "Archive size or SHA-256 mismatch. Obtain the exact selected archive again.")
        files = {}
        seen = set()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
            for member in archive:
                name = member.name
                path = PurePosixPath(name)
                require(not path.is_absolute() and ".." not in path.parts and str(path) == name
                        and name not in seen and (member.isfile() or member.isdir()),
                        "Archive contains an unsupported or duplicate path.")
                seen.add(name)
                if member.isfile():
                    files[name] = archive.extractfile(member).read()
            require(archive.pax_headers.get("comment") == revision,
                    "Archive Git commit does not match --revision. Use git archive on the selected commit.")
        import tomllib

        project = tomllib.loads(files.get("pyproject.toml", b"").decode()).get("project", {})
        manifest = json.loads(files.get("plugin.json", b"{}"))
        version = project.get("version")
        require(project.get("name") == NAME and isinstance(version, str) and VERSION.fullmatch(version)
                and project.get("requires-python") == ">=3.11" and project.get("dependencies") == []
                and project.get("scripts", {}).get("adp") == "adp.cli:main"
                and manifest.get("name") == NAME and manifest.get("version") == version
                and manifest.get("repository") == "https://github.com/oduwan/adp_codex"
                and ENGINE_ENTRYPOINT | {SKILL, "docs/ARCHITECTURE.md"} <= files.keys(),
                "Engine, portable plugin or package version does not match the ADP distribution contract.")
        receipt = {
            "revision": revision, "sha256": expected, "version": version,
            "engine": {name: digest(body) for name, body in files.items() if engine_file(name)},
            "plugin": {name: digest(body) for name, body in files.items() if plugin_file(name)},
        }
        return cls(files, receipt)


def safe_directory(path: Path, uid: int, *, home: Path | None = None, private: bool = False) -> None:
    require(path.is_absolute() and path.resolve() == path and path != Path("/"),
            "Use an absolute, normalized directory without symbolic links.")
    for parent in (path, *path.parents):
        marker = parent / ".git"
        require(not (marker.is_file() or marker.is_symlink() or (marker / "HEAD").is_file()),
                "Installer and Codex directories must be outside Git worktrees.")
    existing = next(parent for parent in (path, *path.parents) if parent.exists())
    info = existing.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == uid and not info.st_mode & 0o022
            and os.access(existing, os.W_OK | os.X_OK),
            f"Directory is not writable and controlled by the invoking UID: {existing}")
    if private and path.exists():
        require(not info.st_mode & 0o077, f"Managed directory must be private (0700): {path}")
    if home is not None:
        for parent in (existing, *existing.parents):
            if parent == home:
                break
            info = parent.stat()
            require(info.st_uid == uid and not info.st_mode & 0o022,
                    f"Directory must be controlled by the invoking UID: {parent}")


def owned_file(path: Path, uid: int) -> os.stat_result:
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == uid and info.st_nlink == 1,
            f"Expected an owned regular file: {path.name}")
    return info


def installed_files(root: Path, expected: dict[str, str]) -> bool:
    return all((path := root / name).is_file() and not path.is_symlink()
               and path.resolve() == path and path.stat().st_size <= MAX_SOURCE
               and digest(path.read_bytes()) == checksum
               for name, checksum in expected.items())


def command(argv: list[str], cwd: Path, label: str, *, seconds: int = 30,
            env: dict[str, str] | None = None, mutation_lock: int | None = None) -> bytes:
    deadline = time.monotonic() + seconds
    output = bytearray()
    inherited = ()
    if mutation_lock is not None:
        # Hold the same flock across abrupt installer exit, including when
        # Codex's CLI shim closes inherited descriptors in its own child.
        program = "import subprocess, sys; raise SystemExit(subprocess.call(sys.argv[1:]))"
        argv = [sys.executable, "-I", "-c", program, *argv]
        inherited = (mutation_lock,)
    with subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          start_new_session=True, pass_fds=inherited) as process:
        try:
            with selectors.DefaultSelector() as readable:
                readable.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    require(remaining > 0 and readable.select(remaining),
                            f"{label} timed out. Check prerequisites and retry.")
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    output.extend(chunk)
                    require(len(output) <= MAX_RESPONSE, f"{label} exceeded the output limit.")
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except (KeyboardInterrupt, OSError, Refusal, subprocess.TimeoutExpired) as exc:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            if isinstance(exc, subprocess.TimeoutExpired):
                raise Refusal(f"{label} timed out. Check prerequisites and retry.") from None
            raise
    require(process.returncode == 0, f"{label} failed. Check its prerequisites in the installation guide.")
    return bytes(output)


@dataclass(frozen=True)
class PluginState:
    registered: bool
    configured: bool
    cached: bool
    enabled: bool


class Codex:
    def __init__(self, executable: str, home: Path, cwd: Path):
        self.executable = executable
        self.home = home
        self.cwd = cwd
        self.mutation_lock = None

    def environment(self) -> dict[str, str]:
        return dict(os.environ, CODEX_HOME=str(self.home))

    def cli(self, *args: str) -> dict:
        return json.loads(command([self.executable, "plugin", *args, "--json"], self.cwd,
                                  "Codex plugin " + " ".join(args[:2]), env=self.environment(),
                                  mutation_lock=self.mutation_lock))

    def probe(self) -> None:
        for args, markers in (
            (("plugin", "marketplace", "add"), ("<SOURCE>", "--json")),
            (("plugin", "marketplace", "remove"), ("<MARKETPLACE_NAME>", "--json")),
            (("plugin", "add"), ("PLUGIN", "--json")),
            (("plugin", "remove"), ("PLUGIN", "--json")),
            (("app-server",), ("--listen", "stdio://")),
        ):
            help_text = command([self.executable, *args, "--help"], self.cwd,
                                "Codex capability probe for " + " ".join(args))
            require(all(marker.encode() in help_text for marker in markers),
                    "Unsupported Codex plugin or app-server command shape. Use a compatible CLI.")

    def config(self) -> dict:
        import tomllib

        path = self.home / "config.toml"
        if not os.path.lexists(path):
            return {}
        require(owned_file(path, os.getuid()).st_size <= MAX_RESPONSE, "Codex config.toml exceeds the inspection bound.")
        config = tomllib.loads(path.read_text())
        require(all(isinstance(config.get(section, {}), dict) for section in ("marketplaces", "plugins")),
                "Unsupported Codex configuration shape.")
        return config

    def require_plugins_enabled(self) -> None:
        output = command([self.executable, "features", "list"], self.cwd,
                         "Inspect effective Codex plugin support", env=self.environment())
        values = [line.split()[-1] for line in output.splitlines() if line.split()[:1] == [b"plugins"]]
        require(values == [b"true"],
                "Codex plugins are disabled or unsupported. Enable plugin support in Codex before installing ADP.")

    def independent_plugins(self, records: dict) -> list[dict]:
        plugins = self.config().get("plugins", {})
        owned = {f"{NAME}@{name}" for name in records}
        return [value for selector, value in plugins.items()
                if selector.startswith(f"{NAME}@") and selector not in owned]

    def observe(self, generation: str, catalog: Path) -> PluginState:
        # Native listing can hide disabled registrations, fail on missing catalogs,
        # or refresh remote caches. Inspect persistence without editing it.
        config = self.config()
        marketplaces = config.get("marketplaces", {})
        registered = generation in marketplaces
        if registered:
            entry = marketplaces[generation]
            require(entry.get("source_type") == "local" and entry.get("source") == str(catalog),
                    "An ADP marketplace name points elsewhere. Restore its original source before retrying.")
        plugin_dir = self.home / "plugins/cache" / generation / NAME
        cached = os.path.lexists(plugin_dir)
        if cached:
            safe_directory(plugin_dir, os.getuid(), home=self.home)
        selector = f"{NAME}@{generation}"
        plugins = config.get("plugins", {})
        configured = selector in plugins
        enabled = configured and plugins[selector].get("enabled", True) is True
        return PluginState(registered, configured, cached, enabled)

    def add(self, name: str, catalog: Path, version: str) -> None:
        selector = f"{NAME}@{name}"
        expected_path = self.home / "plugins/cache" / name / NAME / version
        try:
            registration = self.cli("marketplace", "add", str(catalog))
            if (registration["marketplaceName"] != name or registration["alreadyAdded"] is not False
                    or registration["installedRoot"] != str(catalog) or not self.observe(name, catalog).registered):
                raise UnknownCodexState("Codex marketplace registration or persistence is unconfirmed.")
            result = self.cli("add", selector)
            if (result["pluginId"] != selector or result["version"] != version
                    or result["installedPath"] != str(expected_path)
                    or self.observe(name, catalog) != PluginState(True, True, True, True)):
                raise UnknownCodexState("Codex plugin installation or persistence is unconfirmed.")
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise UnknownCodexState("Codex changed its mutation response or persistence format.") from exc

    def remove(self, name: str, catalog: Path) -> None:
        state = self.observe(name, catalog)
        selector = f"{NAME}@{name}"
        if state.configured or state.cached:
            result = self.cli("remove", selector)
            if result["pluginId"] != selector:
                raise UnknownCodexState("Codex plugin removal identity is unconfirmed.")
            remaining = self.observe(name, catalog)
            require(not remaining.configured and not remaining.cached, "Codex plugin removal is unconfirmed.")
        if state.registered:
            result = self.cli("marketplace", "remove", name)
            if result["marketplaceName"] != name:
                raise UnknownCodexState("Codex marketplace removal identity is unconfirmed.")
        require(self.observe(name, catalog) == PluginState(False, False, False, False),
                "Codex cleanup is unconfirmed.")

    def probe_lifecycle(self) -> None:
        name, version = "adp-managed-probe", "0.0.1"
        catalog = self.cwd / "probe-catalog"
        plugin = catalog / CATALOG_PLUGIN
        skill = plugin / SKILL
        skill.parent.mkdir(parents=True)
        (plugin / "plugin.json").write_text(json.dumps({
            "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
            "name": NAME, "version": version,
            "description": "ADP installer capability check",
            "repository": "https://github.com/oduwan/adp_codex",
        }))
        skill.write_text("---\nname: adp-codex\ndescription: ADP installer capability check\n---\n")
        marketplace = catalog / ".agents/plugins/marketplace.json"
        marketplace.parent.mkdir(parents=True)
        marketplace.write_text(json.dumps(marketplace_payload(name)))
        probe = Codex(self.executable, self.cwd / "probe-codex-home", self.cwd)
        probe.home.mkdir()
        probe.add(name, catalog, version)
        expected = probe.home / "plugins/cache" / name / NAME / version / SKILL
        require(any(entry.get("path") == str(expected) and entry.get("enabled") is True for entry in probe.skills()),
                "The disposable Codex skill could not be discovered and enabled.")
        probe.remove(name, catalog)

    def skills(self) -> list[dict]:
        # A new stdio session, with only initialize and skills/list. No thread or model turn.
        argv = [self.executable, "app-server", "--listen", "stdio://"]
        with subprocess.Popen(argv, cwd=self.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, start_new_session=True, env=self.environment()) as process:
            with selectors.DefaultSelector() as readable:
                readable.register(process.stdout, selectors.EVENT_READ)
                buffer = bytearray()
                total = 0

                def exchange(requests, response_id):
                    nonlocal total
                    for request in requests:
                        process.stdin.write(json.dumps(request).encode() + b"\n")
                    process.stdin.flush()
                    deadline = time.monotonic() + 25
                    while (remaining := deadline - time.monotonic()) > 0:
                        while b"\n" in buffer:
                            line, _, rest = buffer.partition(b"\n")
                            buffer[:] = rest
                            response = json.loads(line)
                            if response.get("id") == response_id:
                                require("result" in response, "Codex refused fresh skills/list discovery.")
                                return response["result"]
                        if readable.select(remaining):
                            chunk = os.read(process.stdout.fileno(), 65536)
                            total += len(chunk)
                            require(chunk and total <= MAX_RESPONSE,
                                    "Codex discovery exited or exceeded the response bound.")
                            buffer.extend(chunk)
                    raise Refusal("Fresh Codex skill discovery timed out.")

                try:
                    exchange([{"id": 1, "method": "initialize", "params": {
                        "clientInfo": {"name": "adp-installer", "version": "1"}}}], 1)
                    result = exchange([{"method": "initialized"},
                                       {"id": 2, "method": "skills/list", "params": {
                                           "cwds": [str(self.cwd)], "forceReload": True}}], 2)
                    entries = result["data"]
                    require(len(entries) == 1 and entries[0]["cwd"] == str(self.cwd),
                            "Unsupported Codex skill listing shape.")
                    return entries[0]["skills"]
                finally:
                    process.stdin.close()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()


class Installation:
    def __init__(self, root: Path, codex: Codex):
        self.root = root
        self.codex = codex
        self.state = root / "state.json"
        self.link = root / "current"

    @contextmanager
    def lock(self, *, write=False):
        import fcntl

        if write:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self.root.exists():
            yield
            return
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            if write:
                self.codex.mutation_lock = fd
            yield
        except BlockingIOError:
            raise Refusal("Another ADP installer is operating on this directory. Retry when it finishes.") from None
        finally:
            if write:
                self.codex.mutation_lock = None
            os.close(fd)

    def load(self) -> tuple[dict, str | None]:
        if not os.path.lexists(self.state):
            require(not os.path.lexists(self.link), "Missing ADP ownership receipt. Preserve the installation for inspection.")
            return {}, None
        info = owned_file(self.state, os.getuid())
        require(info.st_size <= MAX_RESPONSE and not info.st_mode & 0o077, "Invalid ADP ownership receipt permissions or size.")
        data = json.loads(self.state.read_bytes())
        records = data["generations"]
        require(data["schema"] == 1 and data["codex_home"] == str(self.codex.home)
                and isinstance(records, dict) and len(records) <= 2,
                "Installation belongs to a different CODEX_HOME or uses an unsupported receipt.")
        for name, receipt in records.items():
            require(GENERATION.fullmatch(name) and SHA.fullmatch(receipt["revision"])
                    and HEX.fullmatch(receipt["sha256"]) and VERSION.fullmatch(receipt["version"]),
                    "Invalid ADP generation identity in ownership receipt.")
            require("launcher_sha256" not in receipt or HEX.fullmatch(receipt["launcher_sha256"]),
                    "Invalid engine launcher identity in ownership receipt.")
            for section, valid_name in (("engine", engine_file), ("plugin", plugin_file)):
                entries = receipt[section]
                require(isinstance(entries, dict)
                        and all(valid_name(key) and HEX.fullmatch(value) for key, value in entries.items()),
                        "Invalid ADP file inventory in ownership receipt.")
            require(ENGINE_ENTRYPOINT <= receipt["engine"].keys()
                    and {"plugin.json", SKILL} <= receipt["plugin"].keys(),
                    "Incomplete ADP file inventory in ownership receipt.")
        current = os.readlink(self.link) if os.path.lexists(self.link) else None
        require(current is None or current in records, "Current ADP launcher has no matching ownership receipt.")
        return records, current

    def save(self, records: dict) -> None:
        payload = {"schema": 1, "codex_home": str(self.codex.home), "generations": records}
        with tempfile.NamedTemporaryFile(dir=self.root, prefix=".receipt-", delete=False) as stream:
            pending = Path(stream.name)
            try:
                stream.write(json.dumps(payload, sort_keys=True).encode() + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
                pending.replace(self.state)
            finally:
                pending.unlink(missing_ok=True)
        self.sync_root()

    def sync_root(self) -> None:
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def catalog(self, name: str) -> Path:
        return self.root / name / "catalog"

    def observe(self, name: str) -> PluginState:
        generation = self.root / name
        if os.path.lexists(generation):
            safe_directory(generation, os.getuid(), private=True)
        return self.codex.observe(name, self.catalog(name))

    def cleanup(self, records: dict, name: str) -> None:
        require(not records[name].get("codex_format_unknown"),
                "PARTIAL: Codex mutation format changed. Inspect the retained namespace and receipt before cleanup.")
        self.observe(name)
        try:
            self.codex.remove(name, self.catalog(name))
        except (UnknownCodexState, ValueError, KeyError, TypeError, AttributeError) as exc:
            self.retain_unknown(records, name)
            raise UnknownCodexState("Codex removal response changed. Ownership was retained.") from exc
        cache = self.codex.home / "plugins/cache" / name
        if os.path.lexists(cache):
            safe_directory(cache, os.getuid(), home=self.codex.home)
            require(not any(cache.iterdir()),
                    "Codex left files in the ADP cache namespace. Inspect it before retrying.")
            cache.rmdir()
        generation = self.root / name
        if generation.exists():
            shutil.rmtree(generation)
        self.save({key: value for key, value in records.items() if key != name})
        del records[name]

    def retain_unknown(self, records: dict, name: str) -> None:
        records[name] = dict(records[name], codex_format_unknown=True)
        self.save(records)

    def report(self, name: str, receipt: dict) -> bool:
        plugin = self.observe(name)
        generation = self.root / name
        modern_layout = os.path.lexists(generation / "venv")
        engine = generation / ("venv" if modern_layout else "engine")
        sites = list(engine.glob("lib/python*/site-packages"))
        engine_ok = False
        if len(sites) == 1 and installed_files(sites[0], receipt["engine"]):
            versions = list(sites[0].glob("adp_codex-*.dist-info/METADATA"))
            launcher = generation / "bin/adp"
            if len(versions) == 1 and versions[0].resolve() == versions[0] and launcher.is_file() and launcher.resolve() == launcher:
                metadata = BytesParser().parsebytes(versions[0].read_bytes(), headersonly=True)
                engine_ok = metadata["Name"] == NAME and metadata["Version"] == receipt["version"]
        cache = self.codex.home / "plugins/cache" / name / NAME / receipt["version"]
        catalog = self.catalog(name)
        catalog_files = installed_files(catalog / CATALOG_PLUGIN, receipt["plugin"])
        manifest = catalog / ".agents/plugins/marketplace.json"
        catalog_ok = False
        if catalog_files and manifest.is_file() and manifest.resolve() == manifest:
            try:
                catalog_ok = manifest.stat().st_size <= MAX_RESPONSE and json.loads(manifest.read_bytes()) == marketplace_payload(name)
            except ValueError:
                pass
        plugin_ok = plugin.cached and installed_files(cache, receipt["plugin"])
        print(f"{name} revision={receipt['revision']} version={receipt['version']} sha256={receipt['sha256']}")
        print(f"Engine files match={engine_ok}  Marketplace registered={plugin.registered} ready={catalog_ok}  "
              f"Plugin installed={plugin.cached} configured={plugin.configured} "
              f"enabled={plugin.enabled} matches={plugin_ok}", flush=True)
        discovered = False
        if plugin_ok and catalog_ok and plugin.registered and plugin.enabled:
            selector = f"{NAME}@{name}"
            discovered = any(skill.get("name") in {NAME, f"{NAME}:{NAME}"}
                             and skill.get("path") == str(cache / SKILL)
                             and skill.get("pluginId", selector) == selector
                             and skill.get("enabled") is True for skill in self.codex.skills())
        print(f"Exact enabled skill discovered={discovered}", flush=True)
        if engine_ok:
            try:
                expected_launcher = launcher_script(engine).encode()
                require(launcher.stat().st_size == len(expected_launcher)
                        and launcher.read_bytes() == expected_launcher
                        and digest(expected_launcher) == receipt.get("launcher_sha256"),
                        "Installed engine launcher differs from its receipt.")
                if modern_layout:
                    alias = generation / LAUNCHER_ALIAS
                    require(alias.is_symlink() and os.readlink(alias) == LAUNCHER_LINK
                            and alias.resolve() == launcher,
                            "The compatible ADP launcher path no longer points to the managed launcher.")
                probe = ("import importlib.util, json, sys; "
                         "print(json.dumps([sys.prefix, importlib.util.find_spec('adp').origin]))")
                identity = command([str(engine / "bin/python"), "-I", "-B", "-c", probe],
                                   self.codex.cwd, "Inspect installed engine import origin")
                require(json.loads(identity) == [str(engine), str(sites[0] / "adp/__init__.py")],
                        "Venv imports ADP from a different installation.")
                command([str(launcher), "--help"], self.codex.cwd, "Installed adp --help")
            except (OSError, Refusal, ValueError):
                print("Installed adp launcher or interpreter failed verification.", flush=True)
                engine_ok = False
            else:
                print("Installed adp --help passed.", flush=True)
        return engine_ok and plugin.registered and catalog_ok and plugin_ok and plugin.enabled and discovered


    def stage(self, name: str, source: Source) -> None:
        generation = self.root / name
        generation.mkdir(mode=0o700)
        catalog = self.catalog(name)
        engine = generation / "venv"
        with tempfile.TemporaryDirectory(dir=self.codex.cwd) as scratch:
            build = Path(scratch) / "source"
            build.mkdir()
            for name_in_source, data in source.files.items():
                if name_in_source == "pyproject.toml" or engine_file(name_in_source):
                    file = build / name_in_source
                elif plugin_file(name_in_source):
                    file = catalog / CATALOG_PLUGIN / name_in_source
                else:
                    continue
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)
            pip_env = {key: value for key, value in os.environ.items() if key in {
                "HOME", "PATH", "LANG", "LC_ALL", "HTTPS_PROXY", "HTTP_PROXY",
                "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR"}}
            pip_env["PIP_CONFIG_FILE"] = os.devnull
            pip_env["TMPDIR"] = scratch
            command([sys.executable, "-I", "-m", "venv", str(engine)], self.codex.cwd,
                    "Create isolated Python environment", seconds=90, env=pip_env,
                    mutation_lock=self.codex.mutation_lock)
            command([str(engine / "bin/python"), "-I", "-m", "pip", "install", "--no-input",
                     "--disable-pip-version-check", "--no-cache-dir", "--no-deps", str(build)],
                    self.codex.cwd, "Build and install ADP (build dependency download may have failed)",
                    seconds=180, env=pip_env, mutation_lock=self.codex.mutation_lock)
        marketplace = catalog / ".agents/plugins/marketplace.json"
        marketplace.parent.mkdir(parents=True)
        marketplace.write_text(json.dumps(marketplace_payload(name)))
        self.codex.add(name, catalog, source.receipt["version"])

    def apply(self, action: str, records: dict, current: str | None, source: Source | None) -> None:
        for name in set(records) - {current}:
            self.cleanup(records, name)
        if action == "uninstall":
            if current:
                self.link.unlink()
                self.sync_root()
                self.cleanup(records, current)
            return
        assert source is not None
        if current and self.same_source(records[current], source) and self.report(current, records[current]):
            print("Selected ADP installation is already verified.")
            return

        name = f"adp-managed-{uuid.uuid4().hex}"
        require(not os.path.lexists(self.root / name)
                and not os.path.lexists(self.codex.home / "plugins/cache" / name)
                and self.observe(name) == PluginState(False, False, False, False),
                "Candidate ADP namespace already exists. Retry to select a fresh namespace.")
        records[name] = source.receipt
        self.save(records)
        try:
            self.stage(name, source)
            generation = self.root / name
            write_launcher(generation)
            launcher = generation / "bin/adp"
            require(owned_file(launcher, os.getuid()).st_size <= MAX_RESPONSE,
                    "Generated adp launcher exceeds the inspection bound.")
            records[name] = dict(source.receipt, launcher_sha256=digest(launcher.read_bytes()))
            self.save(records)
            require(self.report(name, records[name]), "Candidate engine and skill did not both verify.")
            pending = self.root / name / "activate"
            pending.symlink_to(name)
            pending.replace(self.link)
            self.sync_root()
        except UnknownCodexState:
            self.retain_unknown(records, name)
            raise
        except (Refusal, OSError, ValueError, KeyError, TypeError, AttributeError, KeyboardInterrupt):
            if self.load()[1] != name:
                self.cleanup(records, name)
                print("Candidate removed and prior activation preserved.", file=sys.stderr)
            raise
        if current:
            self.cleanup(records, current)

    @staticmethod
    def same_source(receipt: dict, source: Source) -> bool:
        return (receipt["revision"], receipt["sha256"]) == (source.receipt["revision"], source.receipt["sha256"])


def run(args: argparse.Namespace) -> None:
    require(sys.version_info >= (3, 11), "Python 3.11 or newer is required. Invoke this script with that interpreter.")
    require(sys.platform == "linux", "The ADP installer supports Linux and WSL2.")
    uid = os.getuid()
    require(uid != 0 and uid == os.geteuid(), "Run as your ordinary user, outside sudo or root.")
    os.umask(0o077)
    home = Path(os.environ.get("HOME", ""))
    require(home.is_dir(), "Set HOME to your owned home directory.")
    root = home / MANAGED
    codex_home = Path(os.environ.get("CODEX_HOME", str(home / ".codex")))
    require(codex_home.is_relative_to(home) and codex_home != home
            and not codex_home.is_relative_to(root) and not root.is_relative_to(codex_home),
            "CODEX_HOME must be an owned home subdirectory separate from managed ADP files.")
    safe_directory(home, uid)
    safe_directory(root, uid, home=home, private=True)
    safe_directory(codex_home, uid, home=home)
    for relative in ("plugins/cache", ".tmp/marketplaces"):
        safe_directory(codex_home / relative, uid, home=home)
    if args.action != "verify" and os.path.lexists(codex_home / "config.toml"):
        config = codex_home / "config.toml"
        owned_file(config, uid)
        require(os.access(config, os.W_OK), "Codex config.toml is not writable.")
    executable = shutil.which("codex")
    require(executable, "Install a compatible Codex CLI and put it on PATH.")
    executable = os.path.abspath(executable)
    source = None
    if args.action in {"install", "upgrade"}:
        require(args.source and args.revision and args.sha256, "Specify --source, --revision and --sha256.")
        import importlib.util

        require(all(importlib.util.find_spec(module) for module in ("venv", "ensurepip")),
                "Install the venv and ensurepip support for your Python interpreter.")
        source = Source.read(args.source, args.revision, args.sha256)
    with tempfile.TemporaryDirectory(prefix="adp-install-", dir="/tmp") as scratch:
        codex = Codex(executable, codex_home, Path(scratch))
        installation = Installation(root, codex)
        codex.probe()
        with installation.lock():
            records, current = installation.load()
            unowned = codex.independent_plugins(records)
            if unowned:
                print("An independently installed ADP plugin is present.")
            existing_cli = shutil.which("adp")
            if existing_cli and not Path(existing_cli).resolve().is_relative_to(root):
                print("An independently installed adp command is on PATH. Use the managed launcher path for ADP.")
            if args.action == "verify":
                if current is None:
                    print("No active managed ADP engine.")
                inactive = set(records) - {current}
                for name in sorted(inactive):
                    print(f"PARTIAL: pending cleanup of {name}.", flush=True)
                verified = current is not None and installation.report(current, records[current])
                for name in sorted(inactive):
                    print(installation.observe(name))
                require(verified and not inactive, "ADP verification incomplete. Use install, upgrade or uninstall to reconcile.")
                return
            for name, receipt in records.items():
                print(f"Existing generation {name} revision={receipt['revision']} "
                      f"launcher present={(root / name / 'bin/adp').is_file()} "
                      f"{installation.observe(name)}")
        if source:
            require(not any(row.get("enabled") is not False for row in unowned),
                    "An independently installed ADP plugin is enabled. Disable it in Codex before installing a managed copy.")
            codex.require_plugins_enabled()
            if current and args.action == "install":
                require(installation.same_source(records[current], source),
                        "A different ADP source is active. Use upgrade explicitly.")
            if not current and args.action == "upgrade":
                raise Refusal("No active managed installation. Use install.")
            command([executable, "login", "status"], codex.cwd, "Codex login status")
            github = shutil.which("gh")
            require(github, "Install GitHub CLI and authenticate for github.com.")
            login = command([os.path.abspath(github), "api", "--hostname", "github.com",
                             "user", "--jq", ".login"], codex.cwd,
                            "Read-only GitHub authentication check (authenticate gh for github.com)")
            require(re.fullmatch(rb"[a-zA-Z0-9_-]+\s*", login), "GitHub authentication could not be confirmed.")
            print(f"Source {source.receipt['revision']} SHA-256 {source.receipt['sha256']} "
                  f"version {source.receipt['version']}")
        if source or records:
            codex.probe_lifecycle()
        print(f"Plan for UID {uid}: {args.action} managed engine files under {root} and owned "
              f"ADP plugin entries in {codex_home}. Install/upgrade enables the selected skill. "
              "Any inactive owned generations will be reconciled.", flush=True)
        if args.dry_run or (args.action == "uninstall" and not records):
            return
        if not args.yes:
            require(sys.stdin.isatty() and input("Apply this plan? [y/N] ").strip().lower() in {"y", "yes"},
                    "Plan declined. Pass --yes to authorize this operation non-interactively.")
        with installation.lock(write=True):
            safe_directory(root, uid, home=home, private=True)
            require(installation.load() == (records, current),
                    "Installation changed after preflight. Review the new plan and retry.")
            if source:
                require(not any(row.get("enabled") is not False for row in codex.independent_plugins(records)),
                        "An independently installed ADP plugin became enabled. Review the new plan and retry.")
                codex.require_plugins_enabled()
            try:
                installation.apply(args.action, records, current, source)
            except (Refusal, OSError, ValueError, KeyError, TypeError, AttributeError, KeyboardInterrupt):
                print("Operation interrupted or failed. Run verify for observed state. "
                      "Retained ownership receipts identify any pending cleanup.", file=sys.stderr)
                raise
        if args.action == "uninstall":
            print("Owned engine and plugin removed.")
        else:
            print(f"Engine launcher: {root / 'current/bin/adp'}")


def interrupt_on_term(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="action", required=True)
    for name in ("install", "upgrade", "verify", "uninstall"):
        sub = subcommands.add_parser(name)
        if name in {"install", "upgrade"}:
            sub.add_argument("--source", type=Path, required=True, help="Local uncompressed Git commit archive")
            sub.add_argument("--revision", required=True, help="Selected full Git commit SHA")
            sub.add_argument("--sha256", required=True, help="Independently obtained archive SHA-256")
        if name != "verify":
            consent = sub.add_mutually_exclusive_group()
            consent.add_argument("--dry-run", action="store_true", help="Inspect the plan without applying it")
            consent.add_argument("--yes", action="store_true", help="Authorize the printed plan without a prompt")
    signal.signal(signal.SIGTERM, interrupt_on_term)
    try:
        run(parser.parse_args())
    except Refusal as exc:
        print(f"ADP install: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError, AttributeError, tarfile.TarError, KeyboardInterrupt) as exc:
        # Child diagnostics and parsed data can contain operator-private configuration.
        print(f"ADP install: operation refused ({type(exc).__name__}). Check the source, paths and Codex command shape.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
