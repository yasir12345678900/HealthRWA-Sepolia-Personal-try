"""The final run of the HALAH prototype: every scenario of the scenario list, through the running application, with
one evidence folder.

    python3 tools/final_run.py                 runs the stage that is due, and says which one that is
    python3 tools/final_run.py --stage 2       runs one stage (1, 2, 3, or close for the closing evidence alone)
    python3 tools/final_run.py --only S6-03,S6-04     runs these scenarios alone
    python3 tools/final_run.py --same-day      a trial: runs stage 3 on the day of the transition. CS-08, the request
                                               "the following day", is then recorded as failed
    python3 tools/final_run.py --accept-build-change   continues a run although the files of the build have changed
                                               since its first start. README.md of the folder names the difference
    FINAL_RUN_OUT=<folder>  or  --out <folder>  names the evidence folder (default: evidence/final_run_<date>_<network>)

Nothing is typed that the configuration holds. The tool reads RPC_URL, CONTRACT_V4_ADDRESS, VERIFIER_ADDRESS,
POSEIDON_ADDRESS, GROTH16_VERIFIER_ADDRESS and CHAIN_ID from the environment or from the .env file of the repository,
as the application does, and stops with one plain sentence when something is missing. It starts its own instance of
the application on a new database inside the evidence folder, drives it in a browser (Playwright), and reads what
each step did from the audit ledger of that database, from the receipts and from the answers of the calls.

The application holds the key and sends every transaction of the run. The tool sends none: it reads the chain, and
the attacks on the deployed contracts are made as calls (eth_call), which return the refusal and send nothing. The
scenarios that have no screen are run with the functions of the same build, on copies of the records and with a
ledger of the tool. The tool writes to one store of the application only: the credential status list, in the step
of scenario S5-11 where the issuer revokes one demonstration credential.

The scenario list is tools/final_run_scenarios.json: for each scenario its class, its steps, the expected decision
and deny code, and its evidence. A scenario passes when what was observed equals what the list expects. A scenario
that fails or cannot be carried out is recorded with its reason, and the run goes on with the next one.

A run that is started again on the same folder is continued. What passed is not run again, and a scenario that broke
off is tried again: the tool reads the ledger first, and a step that the earlier attempt made and recorded (a request,
an approval, an attestation, a revocation, a take-over) is not made a second time. The remark column of the summary
says so. A screenshot keeps the name of its step only when the ledger shows the outcome that the step expects.

One run is the work of one build. At its first start the tool notes the commit and a checksum of the files that the
application and the tool execute (run_state.json, "build"), and it compares them at every later start and at the
closing. The application reads its files again at every new browser session, so do not pull and do not edit the
repository until the run is closed. A later start on changed files stops and names them.

The exit code is 0 when no scenario failed or broke off and, when the start made the closing evidence, the automated
test suite passed and every decision of the ledger was taken at the block timestamp. Otherwise it is 1, and the last
lines say why.

Stages. Stage 1 runs on the day of the run. Stage 2 needs the midnight after it, because two consents pass to the
patient's own authority on that day. Stage 3 needs the following day. On Sepolia the tool is started once for each
stage, with the same folder. On a chain whose time can be moved (a local test chain) the three stages run in one go.

The evidence folder: README.md, preflight, summary/, screens/, ledger/, service/, chain/, links, verification/,
tests/, timings/ and app/ (the stores of the run, which are not evidence to publish).
"""
import argparse
import copy
import csv
import hashlib
import importlib.metadata
import json
import os
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

SCENARIO_FILE = os.path.join(REPO, "tools", "final_run_scenarios.json")
SEPOLIA = 11155111
NINE = ("OUT-OF-SCOPE", "PURPOSE-MISMATCH", "CONTEXT-MISMATCH", "PRE-VALIDITY", "POST-VALIDITY", "AWAITING-TRIGGER",
        "TRANSITION-PENDING", "EXPIRED", "REVOKED")
PASS, FAIL, ERROR, NOT_RUN = "PASS", "FAIL", "ERROR", "NOT RUN"
# The settings the run needs, with what to do when one is missing.
SETTINGS = {
    "RPC_URL": "the JSON-RPC endpoint of the chain",
    "CONTRACT_V4_ADDRESS": "the address of ConsentSBTv4 (python3 -m blockchain.deploy_v4 writes it)",
    "VERIFIER_ADDRESS": "the address of ConsentDecisionVerifier (python3 -m blockchain.deploy_v4 writes it)",
    "POSEIDON_ADDRESS": "the address of the Poseidon contract (python3 -m blockchain.deploy_v4 writes it)",
    "GROTH16_VERIFIER_ADDRESS": "the address of the Groth16 verifier (python3 -m blockchain.deploy_v4 writes it)",
    "PRIVATE_KEY": "the key of the wallet that owns ConsentSBTv4, which the application signs with",
}
# What a child process must not inherit: the test suite must not write into the database of the run or reach the chain.
RUN_SETTINGS = ("FINAL_RUN_OUT", "HALAH_DB_PATH", "HALAH_STATUS_LIST_PATH", "HALAH_VAULT_PATH", "HALAH_KEYSTORE_PATH", "PRIVATE_KEY", "RPC_URL",
                "CONTRACT_ADDRESS", "CONTRACT_V4_ADDRESS", "VERIFIER_ADDRESS", "POSEIDON_ADDRESS", "GROTH16_VERIFIER_ADDRESS",
                "CONTRACT_V4_DEPLOY_BLOCK", "CHAIN_ID")
# Gas of one whole run, rounded up: 11 mints, 5 revocations and 8 verifications at the gas read on a local chain.
ESTIMATED_GAS = 15_000_000
CLINICIAN, REGISTRAR = "did:hospital:001", "did:hospital:002"
FIELD_FORMAT = "%Y-%m-%d %H:%M:%S"
START_MARGIN = 60          # a consent starts this many seconds before the time of the chain at its creation
MIN_BEFORE_MIDNIGHT = 90   # minutes that stage 1 needs before the midnight on which the transitions fall due
# The Streamlit whose widgets the screen actions of tools/final_run_screens.py were written for and rehearsed with.
MADE_WITH_STREAMLIT = "1.67.0"
SNARKJS = "snarkjs@0.7.4"  # as zk/build_decision.sh installs it
PACKAGES = ("streamlit", "web3", "playwright", "eth-tester")
# The files that the application and the tool execute: one run is the work of one build of them.
BUILD_FILES = ("app.py", "halah_theme.py", "services", "blockchain", "database", "models", "zk/prove_decision.js",
               "zk/verify_decision.js", "zk/prove.js", "zk/verify.js", "zk/poseidon_cli.js", "data/credentials/demo_credentials.json",
               "tools/final_run.py", "tools/final_run_screens.py", "tools/final_run_scenarios.json", "tools/verify_poc.py")
BUILD_SUFFIXES = (".py", ".json")          # of the files in the folders above: the code and the compiled contracts


class Stop(Exception):
    """The run cannot go on. The message is one plain sentence that names what is missing."""


class NotRun(Exception):
    """A scenario cannot be run because something it needs is missing. The message gives the reason."""


# ---------------------------------------------------------------------------------------------------------
# What needs no chain and no browser (the automated tests call these)
# ---------------------------------------------------------------------------------------------------------
def load_scenarios(path=SCENARIO_FILE):
    """The scenario list: (about, scenarios). Stops when the file is missing or is not the list."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data["about"], data["scenarios"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise Stop(f"The scenario list {path} cannot be read ({error}).") from None


def missing_settings(env):
    """One plain sentence for each setting the run needs and the configuration does not hold."""
    return [f"{name} is not set: {what}." for name, what in SETTINGS.items() if not (env.get(name) or "").strip()]


def child_environment(env, remove=RUN_SETTINGS):
    """The environment of a child process that must not use the stores or the chain of the run (the test suite)."""
    return {name: value for name, value in env.items() if name not in remove}


def compare(scenario, observed):
    """PASS when the observed values equal the expected ones, else FAIL: (result, the differences).
    `expected_check` of the scenario names the values. `failed_checks_include` asks for these checks among the
    failed ones. The deny code must equal the expected one, and null means that none was recorded. Every entry
    of observed["checks"] (further checks of the scenario, name -> true or false) must be true."""
    differences = []
    for name, expected in (scenario.get("expected_check") or {}).items():
        if name == "failed_checks_include":
            got = observed.get("failed_checks")
            if not isinstance(got, list) or not all(check in got for check in expected):
                differences.append(f"failed checks {got}, expected to include {expected}")
        elif observed.get(name) != expected:
            differences.append(f"{name}: observed {observed.get(name)!r}, expected {expected!r}")
    if observed.get("deny_code") != scenario.get("deny_code"):
        differences.append(f"deny code: observed {observed.get('deny_code')!r}, expected {scenario.get('deny_code')!r}")
    differences += [f"check failed: {name}" for name, good in (observed.get("checks") or {}).items() if good is not True]
    return (FAIL if differences else PASS), differences


def window(kind, now):
    """Start and expiry of a consent as the form takes them, from the wording of the scenario list."""
    start = now - timedelta(seconds=START_MARGIN)
    if kind == "now + 2 days to now + 30 days":
        return now + timedelta(days=2), now + timedelta(days=30)
    if kind == "now to now + 290 seconds":
        return start, start + timedelta(seconds=290)
    return start, start + timedelta(days=30)


def eighteen_tomorrow(now):
    """The date of birth of a patient who turns eighteen on the day after `now`."""
    day = (now + timedelta(days=1)).date()
    try:
        return day.replace(year=day.year - 18)
    except ValueError:                         # 29 February
        return day.replace(year=day.year - 18, month=3, day=1)


def next_midnight(moment):
    return datetime.combine(moment.date() + timedelta(days=1), datetime.min.time())


def test_results(junit_path):
    """The outcome of each automated test of one run, from its JUnit file: "tests/file.py::name" -> passed,
    failed or skipped."""
    found = {}
    try:
        root = ElementTree.parse(junit_path).getroot()
    except (OSError, ElementTree.ParseError):
        return found
    for case in root.iter("testcase"):
        file_name = (case.get("classname") or "").replace(".", "/") + ".py"
        outcome = "passed"
        for child in case:
            if child.tag in ("failure", "error"):
                outcome = "failed"
            elif child.tag == "skipped":
                outcome = "skipped"
        found[f"{file_name}::{case.get('name')}"] = outcome
    return found


def tests_of(scenario, results):
    """The automated tests that a scenario names in its evidence, each with its result in this run."""
    named = []
    for entry in scenario.get("evidence", []):
        if not entry.startswith("test: "):
            continue
        node = entry[6:].split(" ")[0].rstrip(",")
        if "::" in node:
            name = node.split("::")[1]
            # a parametrized test is in the results once for each of its cases, as name[case]
            cases = [o for case, o in results.items() if case.startswith(node + "[")]
            if node in results:
                named.append(f"{name}: {results[node]}")
            elif cases:
                named.append(f"{name}: {cases.count('passed')} passed, {cases.count('failed')} failed")
            else:
                named.append(f"{name}: not in this run")
        else:
            of_file = [o for name, o in results.items() if name.startswith(node + "::")]
            named.append(f"{node}: {of_file.count('passed')} passed, {of_file.count('failed')} failed"
                         if of_file else f"{node}: not in this run")
    return named


def decision_words(values):
    """The decision of a scenario as the summary shows it: the outcome and, in brackets, the reason that belongs
    to it when the scenario has one that is not a deny code: the words of the contract, the predicates of the
    statement that do not hold, the reason of a refused revocation or approval."""
    outcome = str(values.get("outcome") or "")
    reasons = []
    for name, label in (("reason_text", ""), ("failed_predicates", ""), ("reason", ""), ("approval_reason", ""),
                        ("reason_on_reissue", "on the re-issue: "), ("new_proof", "new proof: ")):
        value = values.get(name)
        if value:
            reasons.append(label + (", ".join(str(v) for v in value) if isinstance(value, (list, tuple)) else str(value)))
    return f"{outcome} ({'; '.join(reasons)})" if outcome and reasons else outcome


SUMMARY_COLUMNS = ("scenario", "chapter", "section", "class", "attack", "what", "runs in", "expected decision",
                   "expected deny code", "observed decision", "observed deny code", "observed failed checks", "result",
                   "consent", "blocks", "transactions", "evidence files", "automated tests", "remark")


def summary_rows(scenarios, results, tests=None):
    """One row of the summary table for each scenario of the list, in the order of the list. A scenario without
    a result is NOT RUN."""
    rows = []
    for s in scenarios:
        r = results.get(s["id"]) or {"result": NOT_RUN, "message": "not reached in this run"}
        observed = r.get("observed") or {}
        failed = observed.get("failed_checks")
        remark = "; ".join(x for x in [r.get("message")] + list(r.get("differences") or []) + list(r.get("notes") or []) if x)
        rows.append({
            "scenario": s["id"], "chapter": s.get("chapter"), "section": s.get("section"), "class": s.get("class"),
            "attack": s.get("attack") or "", "what": s.get("what"), "runs in": ", ".join(s.get("runs_in", [])),
            "expected decision": decision_words(s.get("expected_check") or {}),
            "expected deny code": s.get("deny_code") or "",
            "observed decision": decision_words(observed),
            "observed deny code": observed.get("deny_code") if observed.get("deny_code") in NINE else "",
            "observed failed checks": ", ".join(failed) if isinstance(failed, list) else "",
            "result": r.get("result", NOT_RUN), "consent": ", ".join(c[:8] for c in r.get("consents", [])),
            "blocks": ", ".join(str(b) for b in r.get("blocks", [])),
            "transactions": ", ".join(t[:12] + "..." for t in r.get("transactions", [])),
            "evidence files": ", ".join(r.get("evidence", [])),
            "automated tests": "; ".join(tests_of(s, tests or {})), "remark": remark})
    return rows


def count_results(rows):
    return {name: sum(1 for r in rows if r["result"] == name) for name in (PASS, FAIL, ERROR, NOT_RUN)}


def write_summary(folder, scenarios, results, tests=None):
    """Write summary.csv, summary.md and summary.json into `folder` and return the counts of the results."""
    os.makedirs(folder, exist_ok=True)
    rows = summary_rows(scenarios, results, tests)
    with open(os.path.join(folder, "summary.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    counts = count_results(rows)
    by_class = {}
    for row in rows:
        by_class.setdefault(row["class"], {name: 0 for name in (PASS, FAIL, ERROR, NOT_RUN)})[row["result"]] += 1
    lines = ["# Summary of the final run", "",
             f"{len(rows)} scenarios: " + ", ".join(f"{counts[name]} {name}" for name in (PASS, FAIL, ERROR, NOT_RUN)) + ".", "",
             "| Class | Scenarios | PASS | FAIL | ERROR | NOT RUN |", "|---|---|---|---|---|---|"]
    lines += [f"| {name} | {sum(c.values())} | {c[PASS]} | {c[FAIL]} | {c[ERROR]} | {c[NOT_RUN]} |" for name, c in by_class.items()]
    shown = ("scenario", "class", "what", "expected decision", "expected deny code", "observed decision",
             "observed deny code", "observed failed checks", "result", "evidence files", "remark")
    lines += ["", "| " + " | ".join(shown) + " |", "|" + "---|" * len(shown)]
    lines += ["| " + " | ".join(str(row[c] or "").replace("|", "/").replace("\n", " ") for c in shown) + " |" for row in rows]
    with open(os.path.join(folder, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(folder, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"counts": counts, "by_class": by_class, "rows": rows,
                   "observed": {sid: (r.get("observed") or {}) for sid, r in results.items()}}, f, indent=1, default=str)
    return counts


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, default=str)


def write_csv(path, columns, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def versions():
    """The versions of what the run stands on: the packages and node."""
    found = {}
    for name in PACKAGES:
        try:
            found[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            found[name] = "not installed"
    try:
        found["node"] = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=30).stdout.strip() or "no answer"
    except (OSError, subprocess.TimeoutExpired):
        found["node"] = "not found"
    return found


def check_machine():
    """Stop with one sentence when the machine lacks what the chain settings do not show: eth-tester, on which the
    automated test suite of the closing evidence runs its on-chain tests, and snarkjs for node in zk/, without
    which the prover gives no proof."""
    try:
        import eth_tester  # noqa: F401
    except ImportError:
        raise Stop("eth-tester is not installed: the suite of the closing evidence would skip most on-chain tests and "
                   'fail five. pip install "eth-tester[py-evm]".') from None
    try:
        loaded = subprocess.run(["node", "-e", "require('snarkjs')"], cwd=os.path.join(REPO, "zk"), capture_output=True,
                                text=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        loaded = False
    if not loaded:
        raise Stop("node cannot load snarkjs in zk/ (zk/node_modules is not in the repository): "
                   f"cd zk && npm install {SNARKJS}.")


def suite_failed(line):
    """True when the one line of the automated test suite does not say that the suite passed: it names a failed
    test or an error, or it is not a result line at all."""
    line = line or ""
    return not re.search(r"\b\d+ passed\b", line) or bool(re.search(r"\b\d+ (failed|errors?)\b", line))


def build_identity(root=None):
    """The build that a start of the tool runs: the commit, whether the working tree has changes, and a checksum of
    every file that the application and the tool execute (BUILD_FILES), with one checksum over them all."""
    root = root or REPO
    files = {}
    for entry in BUILD_FILES:
        path = os.path.join(root, entry)
        found = [path] if os.path.isfile(path) else []
        for folder, folders, names in os.walk(path) if os.path.isdir(path) else ():
            folders[:] = [name for name in folders if name != "__pycache__"]
            found += [os.path.join(folder, name) for name in names if name.endswith(BUILD_SUFFIXES)]
        for name in found:
            with open(name, "rb") as f:
                files[os.path.relpath(name, root).replace(os.sep, "/")] = hashlib.sha256(f.read()).hexdigest()
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip() or "unknown"
        changed = bool(subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout.strip())
    except OSError:
        commit, changed = "unknown", None
    whole = hashlib.sha256("\n".join(f"{name} {files[name]}" for name in sorted(files)).encode()).hexdigest()
    return {"commit": commit, "working_tree_changed": changed, "checksum": whole, "files": files}


def build_difference(first, now):
    """The files of the build whose content is not the same in two builds, each with what happened to it."""
    old, new = first.get("files") or {}, now.get("files") or {}
    return [f"{name} ({'new' if name not in old else 'removed' if name not in new else 'changed'})"
            for name in sorted(set(old) | set(new)) if old.get(name) != new.get(name)]


def build_words(build):
    """One line that names a build."""
    tree = {True: " with changes in the working tree", False: "", None: ""}[build.get("working_tree_changed")]
    return f"commit {build.get('commit')}{tree}, checksum {str(build.get('checksum'))[:12]} of {len(build.get('files') or {})} files"


def time_source_words(sources):
    """One line on the source of the time of the decisions, from the check that the closing made on the ledger."""
    if not sources:
        return "Time source of the decisions: not checked yet (the closing checks it)."
    rows, other = sources.get("rows", 0), sources.get("other") or []
    if not other:
        return f"Time source of the decisions: the {rows} STATE_CHECK and DATA_ACCESS rows of the ledger name the block timestamp."
    named = "; ".join(f"{o['action']} {str(o['event_id'])[:8]} ({o.get('scenario') or 'no scenario'}, {o['time_source']})" for o in other)
    return (f"Time source of the decisions: FAILED. {len(other)} of {rows} STATE_CHECK and DATA_ACCESS rows name another "
            f"source than the block timestamp: {named}.")


def end_of_run(run, counts, total, closing=False, say=print):
    """The last lines of a start and its exit code. 0: no scenario failed or broke off and, when this start made the
    closing evidence, the automated test suite passed and every decision was taken at the block timestamp."""
    say(f"Scenarios: {counts[PASS]} PASS, {counts[FAIL]} FAIL, {counts[ERROR]} ERROR, {counts[NOT_RUN]} NOT RUN of {total}.")
    code = 0 if counts[FAIL] == 0 and counts[ERROR] == 0 else 1
    if closing:
        suite = run.state.get("tests") or "no result line"
        failed = suite_failed(suite)
        say(f"Automated test suite: {suite}." + (" THE SUITE DID NOT PASS: see tests/pytest.txt in the evidence folder." if failed else ""))
        sources = run.state.get("time_sources") or {}
        say(time_source_words(sources))
        if failed or sources.get("other"):
            code = 1
    for change in run.state.get("build_changes", []):
        say(f"The build changed during the run ({change['when']}): {', '.join(change['files']) or 'the commit'}. README.md of the folder says so.")
    due = run.due_stage()
    if due != "close" or not run.state.get("closed"):
        say(f"The run is not closed. Next: {'stage ' + str(due) if due != 'close' else 'the closing evidence'}: start the tool again with the same folder.")
    say(f"Summary: {os.path.join(run.out, 'summary', 'summary.md')}")
    return code


def application_command(port):
    """The command that starts the application of the run. The file watcher of Streamlit is switched off: with it, a
    file written under the folders of the application while the run goes on (a compiled cache is enough) leaves a
    notice on the page, and a step would wait for that notice to go."""
    return [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true", "--server.address", "127.0.0.1",
            "--server.port", str(port), "--server.fileWatcherType", "none", "--browser.gatherUsageStats", "false"]


class ToolLedger:
    """The ledger of the tool for the service calls on copies: it has the two functions of the audit ledger and
    keeps its rows in memory. Nothing of it reaches the database of the run."""

    def __init__(self):
        self.rows = []

    def log(self, actor_did, actor_role, action, patient_did, consent_id, scope=None, purpose=None, result="SUCCESS",
            metadata=None, tx_hash=None, block_number=None):
        row = {"timestamp": datetime.now().isoformat(), "actor_did": actor_did, "actor_role": actor_role, "action": action,
               "patient_did": patient_did, "consent_id": consent_id, "scope": scope, "purpose": purpose, "result": result,
               "metadata": metadata, "tx_hash": tx_hash, "block_number": block_number, "ledger": "of the tool"}
        self.rows.append(row)
        return row

    def get(self):
        return self.rows


def keep_nothing(consent):
    """The store of a service call on a copy: the copy is not written anywhere."""


# ---------------------------------------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------------------------------------
class Run:
    def __init__(self, out, about, scenarios, say=print):
        self.out, self.about, self.say = out, about, say
        self.scenarios = {s["id"]: s for s in scenarios}
        self.order = [s["id"] for s in scenarios]
        self.db = os.path.join(out, "app", "halah_final.db")
        self.state_file = os.path.join(out, "run_state.json")
        self.state = {"started": datetime.now().isoformat(timespec="seconds"), "stages": {}, "consents": {}, "done": [],
                      "results": {}, "observed": {}, "kept": {}, "added": {}, "time_moves": [], "closed": False}
        if os.path.exists(self.state_file):
            with open(self.state_file, encoding="utf-8") as f:
                self.state.update(json.load(f))
        self.calls = self.state.setdefault("calls", [])
        self.screens = self.app = self.browser = self.playwright = None
        self.current = None
        # the rows that an attempt of the running part added before it broke off, and those taken from them
        self.earlier, self.reused = set(), set()

    # ---- state and evidence files -------------------------------------------------------------------
    def save(self):
        write_json(self.state_file, self.state)

    def path(self, *parts):
        target = os.path.join(self.out, *parts)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        return target

    def evidence(self, name):
        """Note an evidence file for the scenario that is running."""
        files = self.state["results"].setdefault(self.current, {}).setdefault("evidence", [])
        if name not in files:
            files.append(name)

    def shot(self, name):
        if name:
            self.evidence(f"screens/{name}.png")
        return name

    def remark(self, text):
        """A sentence for the remark column of the scenario that is running: what a continued run did differently."""
        notes = self.state["results"].setdefault(self.current, {}).setdefault("notes", [])
        if text not in notes:
            notes.append(text)

    def keep_shot(self, name, as_expected, what):
        """A screenshot keeps the name of its step only when the ledger shows the outcome that the step expects.
        Otherwise the file is kept as <name>_unexpected.png and the step ends here with `what`, a plain sentence."""
        if as_expected:
            return
        kept = ""
        if name:
            files = self.state["results"].setdefault(self.current, {}).setdefault("evidence", [])
            if f"screens/{name}.png" in files:
                files.remove(f"screens/{name}.png")
            source = os.path.join(self.out, "screens", f"{name}.png")
            if os.path.exists(source):
                os.replace(source, os.path.join(self.out, "screens", f"{name}_unexpected.png"))
                self.evidence(f"screens/{name}_unexpected.png")
                kept = f" The screenshot is kept as screens/{name}_unexpected.png."
        raise RuntimeError(what + "." + kept)

    def replace(self, key, why):
        """Forget the consent `key` of the run, so that the scenario issues a new one. The identifier that is given
        up stays in the state of the run under "replaced", and its rows stay in the ledger."""
        old = self.state["consents"].pop(key)
        self.state.get("specs", {}).pop(key, None)
        self.state.setdefault("replaced", {}).setdefault(key, []).append(old)
        self.remark(f"a new consent {key} was issued in place of {old[:8]}: {why}")
        self.save()

    def service(self, data):
        """Keep the answer of the service calls of the scenario that is running as service/<id>.json."""
        write_json(self.path("service", f"{self.current}.json"), data)
        self.evidence(f"service/{self.current}.json")

    def note(self, **values):
        """What the scenario that is running observed. The values of all its parts are kept together."""
        observed = self.state["observed"].setdefault(self.current, {})
        for name, value in values.items():
            if name == "checks":
                observed.setdefault("checks", {}).update(value)
            else:
                observed[name] = value

    def track(self, consent_id=None, tx=None, block=None):
        r = self.state["results"].setdefault(self.current, {})
        for name, value in (("consents", consent_id), ("transactions", tx), ("blocks", block)):
            if value is not None and value not in r.setdefault(name, []):
                r[name].append(value)

    # ---- the database of the run, read only ------------------------------------------------------------
    def _read(self, query, args=()):
        if not os.path.exists(self.db):
            return []
        connection = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True, timeout=30)
        try:
            return [json.loads(row[0]) for row in connection.execute(query, args)]
        finally:
            connection.close()

    def ledger(self):
        return self._read("SELECT body FROM audit ORDER BY ts")

    def rows(self, consent_id, action=None, result=None):
        return [e for e in self.ledger() if e.get("consent_id") == consent_id and (action is None or e.get("action") == action)
                and (result is None or e.get("result") == result)]

    def record(self, consent_id):
        found = self._read("SELECT body FROM consents WHERE consent_id=?", (consent_id,))
        return found[0] if found else None

    def consent(self, consent_id):
        """The record of a consent as an object of its own: a copy, which the services may change freely."""
        from models.consent import Consent
        row = self.record(consent_id)
        if row is None:
            raise NotRun(f"the record of consent {consent_id} is not in the database of the run")
        return Consent(**{name: value for name, value in row.items() if name in Consent.__dataclass_fields__})

    def wait(self, what, read, seconds=300):
        """Wait until `read` returns something, and return it."""
        end = time.time() + seconds
        while time.time() < end:
            found = read()
            if found:
                return found
            time.sleep(1)
        raise RuntimeError(f"waited {seconds} seconds for {what}")

    # ---- the stores of the run, read only ----------------------------------------------------------------
    def _store_rows(self, file_name, query, args=()):
        path = os.path.join(self.out, "app", file_name)
        if not os.path.exists(path):
            return []
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
        try:
            return connection.execute(query, args).fetchall()
        finally:
            connection.close()

    def sealed_copy(self, consent_id):
        """The sealed copy of a consent as the vault file holds it: module -> blob (ciphertext, nonce, key reference)."""
        rows = self._store_rows(os.path.join("vault", "halah_vault.db"),
                                "SELECT module, body FROM copies WHERE consent_id=? ORDER BY module", (consent_id,))
        return {module: json.loads(body) for module, body in rows}

    def key_references(self, consent_id):
        rows = self._store_rows(os.path.join("keystore", "halah_keys.db"),
                                "SELECT module, key_id FROM keys WHERE consent_id=? ORDER BY module", (consent_id,))
        return dict(rows)

    def destruction_record(self, consent_id):
        rows = self._store_rows(os.path.join("keystore", "halah_keys.db"),
                                "SELECT destroyed_at, body FROM destroyed WHERE consent_id=?", (consent_id,))
        return dict(json.loads(rows[0][1]), destroyed_at=rows[0][0]) if rows else None

    def read_only_vault(self):
        """The vault and the key store of the run, opened so that nothing can be written: SQLite refuses every
        change on these connections. When the run has no store yet, an empty one in memory stands for it."""
        from services import data_vault, key_store
        keys_path = os.path.join(self.out, "app", "keystore", "halah_keys.db")
        vault_path = os.path.join(self.out, "app", "vault", "halah_vault.db")
        if not (os.path.exists(keys_path) and os.path.exists(vault_path)):
            return data_vault.DataVault(key_store.KeyStore(None), None)
        keys = object.__new__(key_store.KeyStore)
        keys.path, keys._lock = keys_path, threading.Lock()
        keys._db = sqlite3.connect(f"file:{keys_path}?mode=ro", uri=True, check_same_thread=False, timeout=30)
        vault = object.__new__(data_vault.DataVault)
        vault.key_store, vault.path, vault._lock = keys, vault_path, threading.Lock()
        vault._db = sqlite3.connect(f"file:{vault_path}?mode=ro", uri=True, check_same_thread=False, timeout=30)
        return vault

    def run_store(self):
        """The consent records of the run as a store the services can read. It keeps no change."""
        run = self

        class Store:
            def get(self, consent_id):
                return run.consent(consent_id) if run.record(consent_id) else None

            def update(self, consent):
                pass
            save = update
        return Store()

    def run_ledger(self):
        run = self

        class Ledger:
            def get(self):
                return run.ledger()
        return Ledger()

    # ---- the chain, read only ----------------------------------------------------------------------------
    def connect(self):
        from blockchain import contract_v4 as v4
        self.v4 = v4
        self.token = v4.ConsentContractV4(read_only=True)
        self.w3 = self.token.w3
        self.verifier = v4.DecisionVerifierContract(w3=self.w3, read_only=True)
        self.chain_id = self.w3.eth.chain_id
        self.sepolia = self.chain_id == SEPOLIA
        self.network = "sepolia" if self.sepolia else f"chain{self.chain_id}"

    def same_contracts(self):
        """A run is continued only on the contracts it was started on: its consents hold tokens of those contracts."""
        now = {"token": self.token.address, "verifier": self.verifier.address}
        started = self.state.setdefault("contracts", now)
        if started != now:
            raise Stop(f"The folder {self.out} holds a run that was started on other contracts (ConsentSBTv4 "
                       f"{started.get('token')}, configured now: {now['token']}). Name a new folder for this run with --out "
                       "or FINAL_RUN_OUT.")

    def check_build(self, when, accept=False, root=None):
        """One run is the work of one build. The first start notes the build in the state. A later start and the
        closing compare the files with it: the application reads its files again at every new browser session, so
        a pull or an edit between two stages would give one evidence folder made by two builds. A difference is
        kept in the state, from where README.md names it. A start on changed files stops, unless the change is
        accepted. Returns the files that differ."""
        now = build_identity(root)
        first = self.state.get("build")
        if first is None:
            self.state["build"] = now
            self.save()
            return []
        files = build_difference(first, now)
        if not files and first.get("commit") == now.get("commit"):
            return []
        known = self.state.setdefault("build_changes", [])
        same = [c for c in known if (c["commit"], c["checksum"]) == (now["commit"], now["checksum"])]
        if when != "closing" and files and not accept and not any(c.get("accepted") for c in same):
            raise Stop(f"The files of the build have changed since the first start of this run ({', '.join(files[:8])}"
                       f"{' and ' + str(len(files) - 8) + ' more' if len(files) > 8 else ''}). One run is the work of one build: "
                       "bring the files back as they were (git status shows them) and start again. To continue with the files "
                       "as they are now, start with --accept-build-change: README.md of the folder will name the difference.")
        if not same:
            known.append({"at": datetime.now().isoformat(timespec="seconds"), "when": when, "commit": now["commit"],
                          "checksum": now["checksum"], "files": files, "accepted": bool(accept) and when != "closing"})
        elif accept and when != "closing":
            same[0]["accepted"] = True
        self.save()
        return files

    def check_screens(self):
        """The first page of the application. The tool sets the scope fields through the multiselect as the
        Streamlit it was made with draws it. Another Streamlit draws another one, and every creation of a consent
        would then fail at its scope field: the run stops here and names the version."""
        if not self.screens.drives_multiselect():
            raise Stop(f"The multiselect of Streamlit {versions()['streamlit']} is not the one this tool drives (made with "
                       f"{MADE_WITH_STREAMLIT}): pip install streamlit=={MADE_WITH_STREAMLIT}.")

    def trusted(self):
        """The time of the chain: the timestamp of the latest block, with its evidence."""
        from services import time_source
        return time_source.read_time(time_source.block_provider(self.w3), allow_fallback=False)

    def explorer(self, kind, value):
        return f"https://sepolia.etherscan.io/{kind}/{value}" if self.sepolia else ""

    def move_time(self, target, why):
        """Bring the time of the chain to `target`. On Sepolia the tool waits. On a chain whose time can be moved
        (a local test chain) it moves the time, and it never makes that call on Sepolia."""
        now = self.trusted()["time"]
        if now >= target:
            return
        seconds = int((target - now).total_seconds()) + 2
        if not self.sepolia:
            answer = self.w3.provider.make_request("evm_increaseTime", [seconds])
            if "error" not in answer:
                self.state["time_moves"].append({"at": datetime.now().isoformat(timespec="seconds"), "seconds": seconds, "why": why})
                self.save()
                self.say(f"    the time of the chain was moved by {seconds} seconds ({why})")
                return
        self.say(f"    waiting {seconds} seconds ({why})")
        while self.trusted()["time"] < target:
            time.sleep(min(15, max(1, seconds)))

    def fresh_address(self):
        """An address that owns nothing and is not the owner of any contract. On a local test chain it is given
        test ether first, because that chain refuses a call from an empty address before it reaches the contract."""
        address = self.w3.eth.account.from_key("0x" + secrets.token_hex(32)).address
        self.fund(address)
        return address

    def fund(self, address):
        if not self.sepolia:
            self.w3.provider.make_request("halah_fund", [address, str(10 ** 18)])

    def call(self, label, function, sender, **more):
        """One call (eth_call) to a contract from `sender`. Nothing is sent. Returns the entry of chain/calls.json:
        whether the contract refused the call, and its reason."""
        entry = {"scenario": self.current, "call": label, "function": function.fn_name, "from": sender,
                 "block": self.w3.eth.block_number, "refused": False, "reason": None, "answer": None, **more}
        try:
            entry["answer"] = function.call({"from": sender})
        except Exception as error:
            entry["refused"], entry["reason"] = True, self.v4.revert_reason(error)
        self.calls.append(entry)
        write_json(self.path("chain", "calls.json"), self.calls)
        self.evidence("chain/calls.json")
        return entry

    def read(self, label, function, **more):
        """One read of a contract, kept in chain/calls.json."""
        entry = {"scenario": self.current, "call": label, "function": function.fn_name, "from": None,
                 "block": self.w3.eth.block_number, "refused": False, "reason": None, "answer": function.call(), **more}
        self.calls.append(entry)
        write_json(self.path("chain", "calls.json"), self.calls)
        self.evidence("chain/calls.json")
        return entry["answer"]

    def present(self, label, proof, signals=None):
        """Present a proof to verifyDecision as a call from a fresh address. The contract answers, nothing is sent."""
        a, b, c = self.v4.proof_to_calldata(proof)
        signals = [int(s) for s in (signals if signals is not None else proof["publicSignals"])]
        return self.call(label, self.verifier.contract.functions.verifyDecision(a, b, c, signals), self.fresh_address(),
                         public_signals=dict(zip(self.v4.PUBLIC_SIGNALS, (str(s) for s in signals))))

    def trees(self):
        from services import merkle_service
        leaves = [self.token.consent_of(i) for i in range(1, self.token.consent_count() + 1)]
        return (merkle_service.ConsentTree([leaf["commitment"] for leaf in leaves]),
                merkle_service.RevocationTree([i for i, leaf in enumerate(leaves) if leaf["revoked"]]))

    def prove(self, consent, check=True, **request):
        """A proof of the decision rule for one request, made by the prover of this build against the two trees of
        the chain. It is not submitted."""
        from services import zk_decision_service as zd
        consent_tree, revocation_tree = self.trees()
        request.setdefault("now_ts", self.trusted()["unix"])
        return zd.prove_decision(zd.build_statement(consent, self.token.read_roots, **request), consent_tree, revocation_tree,
                                 check=check)

    def no_proof(self, consent, **request):
        """Ask the prover for a proof that must not exist: first with its statement check, which names the predicates
        that do not hold, then without it, so that the witness goes to the circuit and the circuit refuses it."""
        from services import zk_decision_service as zd
        answer = {"request": {k: v for k, v in request.items()}, "proof_made": False, "failed_predicates": None,
                  "circuit_refused": None, "circuit_answer": None}
        try:
            self.prove(consent, **request)
            answer["proof_made"] = True
        except zd.DecisionProofError as error:
            answer["failed_predicates"] = list(error.failed)
        if answer["failed_predicates"] == ["OPENING"] and not getattr(consent, "commitment_opening", None):
            return answer                          # without an opening there is no witness to give to the circuit
        try:
            self.prove(consent, check=False, **request)
            answer["proof_made"], answer["circuit_refused"] = True, False
        except zd.DecisionProofError as error:
            answer["circuit_answer"] = error.detail
            answer["circuit_refused"] = "assert" in (error.detail or "").lower()
        return answer

    # ---- the application ---------------------------------------------------------------------------------
    def start_application(self, environment):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        log = open(self.path("app", "streamlit.log"), "a", encoding="utf-8")
        self.app = subprocess.Popen(application_command(port), cwd=REPO, env=environment, stdout=log,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        url = f"http://127.0.0.1:{port}"
        for _ in range(120):
            if self.app.poll() is not None:
                raise Stop(f"The application did not start: see {self.path('app', 'streamlit.log')}.")
            try:
                if urllib.request.urlopen(url, timeout=3).status == 200:
                    return url
            except Exception:
                time.sleep(1)
        raise Stop(f"The application did not answer at {url}: see {self.path('app', 'streamlit.log')}.")

    def start_browser(self, url):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise Stop("Playwright for Python is not installed: pip install playwright, then playwright install --with-deps chromium.") from None
        from tools.final_run_screens import Screens
        try:
            self.playwright = sync_playwright().start()
            options = {"executable_path": os.environ["CHROMIUM"]} if os.environ.get("CHROMIUM") else {}
            self.browser = self.playwright.chromium.launch(**options)
        except Exception as error:
            raise Stop(f"The browser did not start ({str(error).splitlines()[0]}): playwright install --with-deps chromium, "
                       "or name a Chromium in the variable CHROMIUM.") from None
        os.makedirs(os.path.join(self.out, "screens"), exist_ok=True)
        self.screens = Screens(self.browser.new_page(viewport={"width": 1440, "height": 900}), url,
                               os.path.join(self.out, "screens"), self.say)

    def stop(self):
        for close in (lambda: self.browser and self.browser.close(), lambda: self.playwright and self.playwright.stop()):
            try:
                close()
            except Exception:
                pass
        if self.app is not None and self.app.poll() is None:
            self.app.terminate()
            try:
                self.app.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.app.kill()

    # ---- the consents of the run -------------------------------------------------------------------------
    def spec(self, key):
        """What the form is given for the consent `key` of the scenario list, at the time of the chain."""
        listed = self.about["consents"][key]
        now = self.trusted()["time"]
        start, expiry = window(listed.get("window", ""), now)
        born = listed.get("birth_date")
        if born and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", born):
            born = eighteen_tomorrow(now).isoformat()
        return {"patient": listed["patient"], "clinician": listed["clinician"], "guardians": listed["guardians"],
                "threshold": listed["threshold"], "scope": listed["scope"], "context": listed.get("context", "AU"),
                "birth_date": born, "trigger": listed.get("trigger"), "start": start.strftime(FIELD_FORMAT),
                "expiry": expiry.strftime(FIELD_FORMAT)}

    def cid(self, key):
        """The identifier of a consent of the run. A scenario that needs a consent which was not created is not run."""
        if key not in self.state["consents"]:
            raise NotRun(f"the consent {key} was not created in this run")
        return self.state["consents"][key]

    def create(self, key, shot_form=None, shot_done=None):
        if key in self.state["consents"]:
            return self.state["consents"][key]
        spec = self.spec(key)
        consent_id = self.screens.create(spec, self.shot(shot_form), self.shot(shot_done))
        if not consent_id:
            raise RuntimeError(f"the form did not create the consent {key}: {self.screens.text()[-300:]}")
        self.state["consents"][key] = consent_id
        self.state.setdefault("specs", {})[key] = spec
        self.save()
        self.track(consent_id)
        self.say(f"    consent {key} = {consent_id}")
        return consent_id

    def approve(self, key, guardian, shot=None):
        consent_id = self.cid(key)
        approved = lambda: [e for e in self.rows(consent_id, "SIGN_CONSENT", "SUCCESS") if e["actor_did"] == guardian]
        if not approved():
            self.screens.approve(consent_id, guardian, self.shot(shot))
            try:
                self.wait(f"the approval of {guardian}", approved, 60)
            except RuntimeError:
                self.keep_shot(shot, False, f"the approval of {guardian} on {key} was not recorded")
        self.track(consent_id)

    def anchored(self, key, shot=None):
        """Wait until the ledger holds the confirmed mint of the consent, and return that row."""
        consent_id, failed = self.cid(key), []

        def confirmed():
            done = self.rows(consent_id, "ONCHAIN_MINT")
            if done and done[-1]["result"] == "SUCCESS":
                return done
            if len(done) > len(failed):            # a failed mint that was not seen before
                failed[:] = done
                why = (done[-1].get("metadata") or {}).get("error")
                if len(done) > 1:
                    raise RuntimeError(f"the mint of {key} failed twice: {why}")
                # the application offers the anchoring again on the Guardian screen: it is submitted once more
                self.say(f"    the mint of {key} failed ({why}). It is submitted once more.")
                self.screens.anchor_again(consent_id)
            return None
        row = self.wait(f"the mint of {key}", confirmed, 600)[-1]
        self.track(consent_id, row["tx_hash"], row["block_number"])
        if shot:
            self.screens.anchored(consent_id, self.shot(shot))
        return row

    def issue(self, key, guardians=None, shot_done=None, shot_anchored=None):
        """Create the consent, let the guardians approve it and wait for its mint."""
        self.create(key, shot_done=shot_done)
        for guardian in (guardians or self.about["consents"][key]["guardians"][:self.about["consents"][key]["threshold"]]):
            self.approve(key, guardian)
        return self.anchored(key, shot_anchored)

    def token_of(self, key):
        """The token of a consent, from the row of its mint (the record loses the link at a revocation)."""
        mints = self.rows(self.cid(key), "ONCHAIN_MINT", "SUCCESS")
        if not mints:
            raise NotRun(f"the consent {key} has no confirmed mint")
        # the row of a mint holds the number, the row of a re-issue at the transition holds it as "SBT-<number>"
        return int(str((mints[-1].get("metadata") or {})["token_id"]).replace("SBT-", ""))

    def earlier_request(self, consent_id, requester, scope, purpose, context):
        """On a second attempt of a part: the DATA_ACCESS row that the attempt which broke off recorded for the same
        requester, scope, purpose and context, or None. Each row is taken once, in the order of the ledger."""
        for e in self.rows(consent_id, "DATA_ACCESS"):
            if e["event_id"] in self.earlier and e["event_id"] not in self.reused and e.get("actor_did") == requester \
                    and e.get("scope") == scope and e.get("purpose") == purpose and (e.get("metadata") or {}).get("context") == context:
                return e
        return None

    def request(self, key, requester=CLINICIAN, scope=("Observation",), purpose="Treatment", context="AU", before=None, after=None,
                taken=None):
        """One request on the Clinician screen. Returns what the ledger recorded for it.
        A request that an earlier attempt of the same part made and recorded is not clicked a second time: its row is
        used, so that no release is made twice. `taken` names such a row when the scenario has found it itself.
        A screenshot whose name says "granted" or "denied" keeps that name only when the row says the same."""
        consent_id = self.cid(key)
        access = taken or self.earlier_request(consent_id, requester, list(scope), purpose, context)
        if access is not None:
            self.reused.add(access["event_id"])
            missing = [name for name in (before, after) if name and not os.path.exists(os.path.join(self.out, "screens", f"{name}.png"))]
            for name in (before, after):
                if name and name not in missing:
                    self.shot(name)
            self.remark(f"the request on {key} was not made a second time: its record of the earlier attempt was used ({access['result']})"
                        + (f", and the screenshot {', '.join(missing)} was not taken" if missing else ""))
        else:
            count = len(self.rows(consent_id, "DATA_ACCESS"))
            self.screens.request(consent_id, requester, list(scope), purpose, context, self.shot(before), self.shot(after))
            access = self.wait("the DATA_ACCESS record", lambda: self.rows(consent_id, "DATA_ACCESS")[count:], 120)[-1]
        rows = self.rows(consent_id)
        if access["event_id"] in self.reused:      # the lifecycle check of that request stands before its row
            rows = rows[:[e["event_id"] for e in rows].index(access["event_id"])]
        checks = [e for e in rows if e["action"] == "STATE_CHECK"
                  and ((e.get("metadata") or {}).get("lifecycle") or {}).get("operation") == "ACCESS"]
        m = access.get("metadata") or {}
        reference = m.get("proof_reference") or {}
        self.track(consent_id, reference.get("tx_hash"), reference.get("block_number"))
        expected = "DENIED" if "_denied" in (after or "") else "GRANTED" if "_granted" in (after or "") else None
        if expected and access["result"] != expected:
            self.note(outcome=access["result"], deny_code=m.get("deny_code"), failed_checks=m.get("failed_checks"))
            self.keep_shot(after, False, f"the request on {key} was {access['result']} and the step {after} expects {expected}")
        return {"outcome": access["result"], "deny_code": m.get("deny_code"), "failed_checks": m.get("failed_checks"),
                "state": checks[-1]["result"] if checks else m.get("consent_state"), "modules_released": m.get("modules_released"),
                "time_source": m.get("time_source"), "proof_verified": m.get("zk_proof_verified"),
                "decision_time": m.get("decision_time"), "requester": access["actor_did"], "scope": access["scope"],
                "purpose": access["purpose"], "context": m.get("context"), "tx_hash": reference.get("tx_hash"),
                "block_number": reference.get("block_number"), "tag": reference.get("tag"),
                "nonce": (reference.get("reference") or {}).get("nonce"), "event_id": access["event_id"]}

    def denied(self, key, **request):
        """A request that the scenario expects to be refused: its outcome, deny code, failed checks and state."""
        got = self.request(key, **request)
        self.note(outcome=got["outcome"], deny_code=got["deny_code"], failed_checks=got["failed_checks"], state=got["state"],
                  modules_released=got["modules_released"], time_source=got["time_source"])
        return got

    def on_copy(self, consent, requester=CLINICIAN, scope=("Observation",), purpose="Treatment", context="AU"):
        """The request path that the Clinician screen calls, on a copy of a record with a ledger of the tool."""
        from services import request_service
        ledger = ToolLedger()
        out = request_service.submit_request(consent, requester, scope, purpose, context, time=self.trusted(),
                                             audit=ledger, save=keep_nothing)
        return {"outcome": out["outcome"], "deny_code": out["deny_code"], "failed_checks": out["failed_checks"],
                "state": out["state"], "modules_released": out["modules"], "rows_in_the_ledger_of_the_tool": ledger.rows}

    def revocation_rows(self, key):
        """The rows of the revocation of a consent: the REVOKE_CONSENT row that revoked it (or, when there is none, the
        last one) and the row of its on-chain revoke."""
        rows = self.rows(self.cid(key))
        revoke = [e for e in rows if e["action"] == "REVOKE_CONSENT"]
        made = [e for e in revoke if e["result"] == "SUCCESS" and (e.get("metadata") or {}).get("revocation") == "REVOKED"]
        onchain = [e for e in rows if e["action"] == "ONCHAIN_REVOKE" and not (e.get("metadata") or {}).get("capacity_transition")]
        return (made[-1] if made else revoke[-1] if revoke else None), (onchain[-1] if onchain else None)

    # ---- the scenarios of Chapter 5 -----------------------------------------------------------------------
    def s5_01(self):
        from services import access_service, state_service
        self.create("K22", "S5-01_01_patient_form", "S5-01_02_patient_created")
        created = self.consent(self.cid("K22"))
        self.approve("K22", "did:parent:A", "S5-01_03_guardian_A_1of2")
        after_one = self.consent(self.cid("K22"))
        self.approve("K22", "did:parent:B", "S5-01_04_guardian_B_2of2_token")
        mint = self.anchored("K22", "S5-01_05_guardian_anchored")
        record = self.consent(self.cid("K22"))
        token = self.token_of("K22")
        transaction = self.w3.eth.get_transaction(mint["tx_hash"])
        data = bytes(transaction["input"])
        stored = self.token.consent_of(token)
        self.read("consents(token) of K22", self.token.contract.functions.consents(token), token=token)
        valid = self.read("checkValid(token) of K22", self.token.contract.functions.checkValid(token), token=token)
        self.note(outcome="ISSUED" if mint["result"] == "SUCCESS" and record.token_id == f"SBT-{token}" else "NOT ISSUED",
                  state=state_service.lifecycle_state(record, self.trusted()["time"]),
                  approvals=f"{len(access_service.guardian_approvals(record))}/{record.threshold}", onchain_mint=mint["result"],
                  checks={"pending with a commitment after creation": created.state == "PENDING_SIGNATURE" and bool(created.commitment),
                          "no token at 1 of 2": not after_one.token_id and len(after_one.signatures) == 1,
                          "the mint input holds the per-consent address and the commitment only":
                              len(data) == 68 and data[16:36] == bytes.fromhex(record.token_address[2:])
                              and int.from_bytes(data[36:68], "big") == int(record.commitment, 16),
                          "the stored commitment is the commitment of the record": stored["commitment"] == int(record.commitment, 16),
                          "checkValid is true": valid is True})

    def issued(self, key):
        from services import access_service, state_service
        record = self.consent(self.cid(key))
        mints = self.rows(self.cid(key), "ONCHAIN_MINT", "SUCCESS")
        self.note(outcome="ISSUED" if mints and str(record.token_id or "").startswith("SBT-") and record.token_address else "NOT ISSUED",
                  state=state_service.lifecycle_state(record, self.trusted()["time"]),
                  approvals=f"{len(access_service.guardian_approvals(record))}/{record.threshold}",
                  onchain_mint=mints[-1]["result"] if mints else None)
        return record

    def s5_02(self):
        self.create("K23", shot_done="S5-02_01_patient_created")
        self.approve("K23", "did:parent:A", "S5-02_02_guardian_A_1of2")
        self.approve("K23", "did:parent:B", "S5-02_03_guardian_B_2of2_token")
        self.anchored("K23")
        self.approve("K23", "did:parent:C", "S5-02_04_guardian_C_after_threshold")
        self.issued("K23")
        consent_id = self.cid("K23")
        self.note(mint_rows=len(self.rows(consent_id, "MINT_SBT")),
                  checks={"one mint on chain": len(self.rows(consent_id, "ONCHAIN_MINT")) == 1,
                          "three approvals recorded": len(self.rows(consent_id, "SIGN_CONSENT", "SUCCESS")) == 3})

    def s5_03(self):
        from services import identity_service
        if not identity_service.verify_identity("did:parent:E", role="guardian").valid:
            raise NotRun("no valid guardian credential for did:parent:E in data/credentials/demo_credentials.json")
        self.create("K35", shot_done="S5-03_01_patient_created")
        self.approve("K35", "did:parent:A")
        self.approve("K35", "did:parent:B", "S5-03_02_guardian_B_2of3_pending")
        pending = self.consent(self.cid("K35"))
        self.approve("K35", "did:parent:C", "S5-03_03_guardian_C_3of3_token")
        self.anchored("K35", "S5-03_04_guardian_anchored")
        self.issued("K35")
        self.note(checks={"no token at 2 of 3": not pending.token_id and len(pending.signatures) == 2})

    def s5_04(self):
        self.create("KPEND", shot_done="S5-04_01_patient_created")
        self.approve("KPEND", "did:parent:A", "S5-04_02_guardian_A_1of2")
        self.denied("KPEND", before="S5-04_03_clinician_before_request", after="S5-04_04_clinician_denied")

    def outside_signer(self, consent, signer):
        """A1: an approval by a party outside G, signed over the commitment, added to a copy of the record."""
        from services import access_service, identity_service, state_service
        signature, address = identity_service.sign_consent_v2(signer, consent.consent_id, consent.commitment)
        consent.signatures.append(signer)
        consent.signature_data[signer] = {"scheme": "EIP-712", "version": 2, "signer": address, "signature": signature}
        decision = self.on_copy(consent)
        return {"signer": signer, "signature_added_to_the_copy": True,
                "approvals_counted": len(access_service.guardian_approvals(consent)),
                "threshold_met": access_service.threshold_met(consent),
                "state": state_service.lifecycle_state(consent, self.trusted()["time"]), "decision": decision}

    def s5_05(self):
        consent_id = self.cid("KPEND")
        offered = self.screens.guardian_options(consent_id, self.shot("S5-05_01_guardian_selector_offers_only_G"))
        answer = self.outside_signer(self.consent(consent_id), "did:parent:C")
        self.service({"called": "sign_consent_v2, guardian_approvals, threshold_met, lifecycle_state, submit_request",
                      "on": f"a copy of the record of KPEND ({consent_id}) at 1 of 2", "selector_offers": offered, **answer})
        self.note(outcome="REFUSED" if answer["decision"]["outcome"] == "DENIED" and not answer["threshold_met"] else "ACCEPTED",
                  approvals_counted=answer["approvals_counted"], threshold_met=answer["threshold_met"],
                  failed_checks=answer["decision"]["failed_checks"], deny_code=answer["decision"]["deny_code"],
                  checks={"the selector offers the guardians of the consent only": offered == self.about["consents"]["KPEND"]["guardians"]})

    def s5_06(self):
        from services import identity_service
        source, target = self.consent(self.cid("K22")), self.consent(self.cid("KPEND"))
        replayed = source.signature_data["did:parent:A"]["signature"]
        verifies = identity_service.verify_signature_v2("did:parent:A", target.consent_id, target.commitment, replayed)
        own = identity_service.verify_signature_v2("did:parent:A", source.consent_id, source.commitment, replayed)
        target.signature_data["did:parent:A"] = dict(target.signature_data["did:parent:A"], signature=replayed)
        decision = self.on_copy(target)
        self.service({"called": "verify_signature_v2, submit_request",
                      "on": f"the approval of did:parent:A on K22 ({source.consent_id}), presented for KPEND ({target.consent_id})",
                      "verifies_for_its_own_consent": own, "verifies_for_the_other_consent": verifies, "decision": decision})
        self.note(outcome="REFUSED" if not verifies and decision["outcome"] == "DENIED" else "ACCEPTED", signature_verifies=verifies,
                  failed_checks=decision["failed_checks"], deny_code=decision["deny_code"],
                  checks={"the signature verifies for its own consent": own is True})

    def s5_07(self):
        from services import access_service
        consent_id = self.cid("KPEND")
        self.screens.approve(consent_id, "did:parent:A", self.shot("S5-07_01_guardian_A_second_approval_refused"))
        rows = [e for e in self.rows(consent_id, "SIGN_CONSENT", "SUCCESS") if e["actor_did"] == "did:parent:A"]
        self.keep_shot("S5-07_01_guardian_A_second_approval_refused", len(rows) == 1,
                       f"the ledger holds {len(rows)} approvals of did:parent:A on KPEND after the second click, and one is expected")
        doubled = self.consent(consent_id)
        doubled.signatures.append("did:parent:A")
        counted = len(access_service.guardian_approvals(doubled))
        self.service({"called": "guardian_approvals, threshold_met", "on": f"a copy of the record of KPEND ({consent_id}) with "
                      "did:parent:A listed twice", "signatures": doubled.signatures, "approvals_counted": counted,
                      "threshold_met": access_service.threshold_met(doubled)})
        self.note(outcome="REFUSED" if len(rows) == 1 and not access_service.threshold_met(doubled) else "ACCEPTED",
                  approvals_counted=counted, sign_rows=len(rows),
                  checks={"the record still holds one approval": self.record(consent_id)["signatures"] == ["did:parent:A"]})

    def s5_08(self):
        token, stranger = self.token.contract, self.fresh_address()
        before = self.token.consent_count()
        answer = self.call("mintConsent by an account that is not the owner", token.functions.mintConsent(stranger, 4242), stranger)
        after = self.read("consentCount afterwards", token.functions.consentCount())
        self.note(outcome="REFUSED" if answer["refused"] else "ACCEPTED", reason_text=answer["reason"],
                  checks={"consentCount is unchanged": after == before})

    def s5_09(self):
        token, stranger, number = self.token.contract, self.fresh_address(), self.token_of("K22")
        answer = self.call("revoke by an account that is not the owner", token.functions.revoke(number), stranger, token=number)
        valid = self.read("checkValid afterwards", token.functions.checkValid(number), token=number)
        self.note(outcome="REFUSED" if answer["refused"] else "ACCEPTED", reason_text=answer["reason"], check_valid_after=valid)

    def s5_10(self):
        token, stranger, number = self.token.contract, self.fresh_address(), self.token_of("K22")
        holder = token.functions.ownerOf(number).call()
        self.fund(holder)
        by_holder = self.call("transferFrom by the holder of the token", token.functions.transferFrom(holder, stranger, number),
                              holder, token=number)
        owner = token.functions.owner().call()
        by_owner = self.call("transferFrom by the owner of the contract", token.functions.transferFrom(holder, stranger, number),
                             owner, token=number)
        still = self.read("ownerOf afterwards", token.functions.ownerOf(number), token=number)
        self.note(outcome="REFUSED" if by_holder["refused"] and by_owner["refused"] else "ACCEPTED", reason_text=by_holder["reason"],
                  checks={"the owner of the contract is refused as well": by_owner["reason"] == "ERC721: caller is not token owner or approved",
                          "the holder is still the per-consent address": still == holder})

    def s5_11(self):
        from eth_account import Account
        from services import credential_status, identity_service
        # at creation: a clinician who holds no credential
        spec = dict(self.spec("KPEND"), clinician="did:hospital:999")
        count = len([e for e in self.ledger() if e["action"] == "CREATE_CONSENT"])
        created = self.screens.create(spec, shot_done=self.shot("S5-11_01_patient_clinician_without_credential"))
        refused_at_creation = created is None and len([e for e in self.ledger() if e["action"] == "CREATE_CONSENT"]) == count
        # at the approval: the issuer revokes the credential of one guardian, then that guardian approves
        consent_id = self.cid("KPEND")
        if identity_service.verify_identity("did:parent:D", role="guardian").valid:
            credential_status.revoke_credential("did:parent:D")
        self.screens.approve(consent_id, "did:parent:D", self.shot("S5-11_02_guardian_D_revoked_credential_refused"))
        rejected = [e for e in self.rows(consent_id, "SIGN_CONSENT", "REJECTED") if e["actor_did"] == "did:parent:D"]
        self.keep_shot("S5-11_02_guardian_D_revoked_credential_refused",
                       bool(rejected) and not [e for e in self.rows(consent_id, "SIGN_CONSENT", "SUCCESS") if e["actor_did"] == "did:parent:D"],
                       "the approval of the guardian whose credential was revoked was not recorded as rejected")
        # at the request: a requester whose credential carries another role
        request = self.request("K22", requester="did:parent:A", after="S5-11_03_clinician_wrong_role_denied")
        # forged credentials, given to Algorithm 5.1
        forger, own = Account.create(), identity_service.get_credential(CLINICIAN)
        changed = copy.deepcopy(identity_service.get_credential("did:parent:A"))
        changed["credentialSubject"]["role"] = "doctor"
        forged = {"signed by a key that is not the issuer's": identity_service.issue_credential(CLINICIAN, "doctor", signer=forger),
                  "from an issuer that is not trusted": identity_service.issue_credential(
                      CLINICIAN, "doctor", issuer_did="did:example:unknown-issuer", signer=forger),
                  "with a changed role claim": changed,
                  "issued to another identifier": identity_service.get_credential(REGISTRAR),
                  "expired": identity_service.issue_credential(
                      CLINICIAN, "doctor", valid_until=(datetime.now() - timedelta(days=1)).isoformat(timespec="seconds"))}
        answers = {name: identity_service.verify_identity(CLINICIAN, role="doctor", credential=credential).as_dict()
                   for name, credential in forged.items()}
        control = identity_service.verify_identity(CLINICIAN, role="doctor", credential=own)
        self.service({"called": "verify_identity('did:hospital:001', role='doctor', credential=<forged>)",
                      "the_genuine_credential": control.result,
                      "forged": {name: {"result": a["result"], "reason": a["reason"]} for name, a in answers.items()}})
        self.note(outcome="REFUSED" if refused_at_creation and rejected and request["outcome"] == "DENIED" else "ACCEPTED",
                  approval_reason=(rejected[-1]["metadata"] or {}).get("reason") if rejected else None,
                  request_failed_checks=request["failed_checks"], deny_code=request["deny_code"],
                  forged_valid=sum(1 for a in answers.values() if a["result"] == "VALID"),
                  checks={"creation is refused": refused_at_creation, "the genuine credential is valid": control.valid,
                          "the record of KPEND is unchanged": self.record(consent_id)["signatures"] == ["did:parent:A"],
                          "the refused approval records the status check": bool(rejected) and
                              (rejected[-1]["metadata"].get("credential_checks") or {}).get("Status_valid") is False})

    # ---- the scenarios of Chapter 6 -----------------------------------------------------------------------
    def s6_01(self):
        got = self.request("K22", before="S6-01_01_clinician_matrix_all_pass", after="S6-01_02_clinician_granted_records")
        self.note(outcome=got["outcome"], deny_code=got["deny_code"], failed_checks=got["failed_checks"], state=got["state"],
                  modules_released=got["modules_released"], time_source=got["time_source"], proof_verified=got["proof_verified"],
                  checks={"the proof reference names a transaction": bool(got["tx_hash"])})

    def s6_02_issue(self):
        self.issue("KGR", shot_anchored="S6-02_01_guardian_anchored")
        got = self.request("KGR", after="S6-02_02_clinician_granted")
        self.note(checks={"the request before the revocation is granted": got["outcome"] == "GRANTED"})

    def s6_02_revoke(self):
        if not self.record(self.cid("KGR"))["revoked"]:               # a continued run does not revoke a second time
            self.screens.guardian_revoke(self.cid("KGR"), "did:parent:B", self.shot("S6-02_03_guardian_B_revoked_alone"))
            self.keep_shot("S6-02_03_guardian_B_revoked_alone", bool(self.record(self.cid("KGR"))["revoked"]),
                           "the guardian's revocation of KGR was not recorded")
        revoke, onchain = self.revocation_rows("KGR")
        m = (revoke or {}).get("metadata") or {}
        if onchain:
            self.track(self.cid("KGR"), onchain.get("tx_hash"), onchain.get("block_number"))
        self.note(outcome=m.get("revocation") if revoke and revoke["result"] == "SUCCESS" else "REFUSED",
                  revoker_role=m.get("revoker_role"), complete=m.get("complete"), onchain_revoke=(onchain or {}).get("result"),
                  checks={"the basis is one guardian before majority": m.get("basis") == "one guardian before majority",
                          "the recipient is notified": m.get("recipients") == [CLINICIAN],
                          "the copy is deleted and its keys are destroyed": (m.get("shredded") or {}).get("shredded") is True})

    def s6_03(self):
        self.denied("K22", scope=["Procedure"], after="S6-03_01_clinician_denied_out_of_scope")

    def s6_04(self):
        got = self.denied("K22", scope=[], after="S6-04_01_clinician_denied_empty_scope")
        self.note(checks={"the row has the scope []": got["scope"] == []})

    def s6_05(self):
        self.denied("K22", purpose="Research", after="S6-05_01_clinician_denied_purpose")

    def s6_06(self):
        self.denied("K22", context="US", after="S6-06_01_clinician_denied_context")

    def s6_07(self):
        self.create("KPRE", shot_done="S6-07_01_patient_created_future_start")
        self.approve("KPRE", "did:parent:A")
        self.approve("KPRE", "did:parent:B")
        self.anchored("KPRE")
        self.denied("KPRE", after="S6-07_02_clinician_denied_pre_validity")

    def s6_08_issue(self):
        self.issue("KEXP", shot_done="S6-08_01_patient_created_5min")
        expiry = datetime.fromisoformat(self.consent(self.cid("KEXP")).expiry_date)
        if self.trusted()["time"] < expiry - timedelta(seconds=45):
            got = self.request("KEXP", after="S6-08_02_clinician_inside_window")
            self.note(inside_the_window=got["outcome"])
        else:
            self.note(inside_the_window="not requested: the window was too near its end")

    def past_expiry(self, key):
        expiry = datetime.fromisoformat(self.consent(self.cid(key)).expiry_date)
        self.move_time(expiry + timedelta(seconds=5), f"the window of {key} passes")
        return expiry

    def s6_08_expired(self):
        expiry = self.past_expiry("KEXP")
        got = self.denied("KEXP", before="S6-08_03_clinician_expired_before_request", after="S6-08_04_clinician_denied_expired")
        self.note(checks={"the decision time is after the expiry": bool(got["decision_time"]) and
                          datetime.fromisoformat(got["decision_time"]) > expiry,
                          "the time is the block timestamp": got["time_source"] == "block-timestamp"})

    def s6_09_create(self):
        self.create("KPOST")
        self.approve("KPOST", "did:parent:A", "S6-09_01_guardian_A_1of2")

    def s6_09_expired(self):
        self.past_expiry("KPOST")
        self.denied("KPOST", after="S6-09_02_clinician_denied_post_validity")

    def trigger_steps(self, consent_id):
        """What the ledger holds of the three steps of S6-10 on a consent: its requests in order, the verified
        attestation, and whether these are a beginning of the scenario (the refused request that waits for the trigger,
        then the attestation, then the granted request)."""
        accesses = self.rows(consent_id, "DATA_ACCESS")
        attested = self.rows(consent_id, "PRESENT_ATTESTATION", "SUCCESS")
        waited = bool(accesses) and accesses[0]["result"] == "DENIED" and (accesses[0].get("metadata") or {}).get("deny_code") == "AWAITING-TRIGGER"
        in_order = (not accesses and not attested) or (waited and len(accesses) == 1) or (
            waited and len(accesses) == 2 and bool(attested) and accesses[1]["result"] == "GRANTED")
        return accesses, attested, in_order

    def s6_10(self):
        # A run that is continued reads the ledger before each step: a step that an earlier attempt made and
        # recorded is not clicked again. A consent on which the scenario cannot be shown any more is given up.
        if "KTRG" in self.state["consents"] and not self.trigger_steps(self.cid("KTRG"))[2]:
            self.replace("KTRG", "an earlier attempt left it in a state from which the scenario cannot be shown")
        self.issue("KTRG", shot_done="S6-10_01_patient_created_with_trigger")
        consent_id = self.cid("KTRG")
        accesses, attested, _ = self.trigger_steps(consent_id)
        first = self.request("KTRG", after="S6-10_02_clinician_denied_awaiting_trigger", taken=accesses[0] if accesses else None)
        self.keep_shot("S6-10_02_clinician_denied_awaiting_trigger", first["deny_code"] == "AWAITING-TRIGGER",
                       f"the request before the attestation was denied with {first['deny_code']} and not with AWAITING-TRIGGER")
        if attested:
            self.remark("the attestation was not made a second time: its record of the earlier attempt was used")
        else:
            self.screens.attest(consent_id, CLINICIAN, self.shot("S6-10_03_clinician_attestation_recorded"))
            self.keep_shot("S6-10_03_clinician_attestation_recorded", bool(self.rows(consent_id, "PRESENT_ATTESTATION", "SUCCESS")),
                           "the attestation of the clinician was not recorded as verified")
        attested = self.rows(consent_id, "PRESENT_ATTESTATION")
        second = self.request("KTRG", after="S6-10_04_clinician_granted_after_attestation", taken=accesses[1] if len(accesses) > 1 else None)
        moves = [e["result"] for e in self.rows(consent_id, "CONDITION_CHECK")]
        self.note(outcome=f"{first['outcome']} then {second['outcome']}", deny_code=first["deny_code"],
                  failed_checks=first["failed_checks"], state=first["state"],
                  attestation=attested[-1]["result"] if attested else None, second_outcome=second["outcome"],
                  checks={"the consent moved into SUSPENDED and back to ACTIVE": moves == ["SUSPENDED", "ACTIVE"],
                          "the attestation is by the clinician": bool(attested) and attested[-1]["actor_did"] == CLINICIAN})

    def s6_11_day_before(self):
        self.issue("KTR", shot_done="S6-11_01_patient_created_minor")
        got = self.request("KTR", after="S6-11_02_clinician_granted_day_before")
        self.note(day_before=got["outcome"],
                  checks={"the request the day before is granted": got["outcome"] == "GRANTED",
                          "the transition is scheduled": bool(self.rows(self.cid("KTR"), "SCHEDULE_TRANSITION"))})

    def s6_11_majority(self):
        self.denied("KTR", before="S6-11_03_clinician_suspended_before_request", after="S6-11_04_clinician_denied_transition_pending")

    def s6_12(self):
        got = self.denied("KGR", before="S6-12_01_clinician_revoked_before_request", after="S6-12_02_clinician_denied_revoked")
        matrix = self.rows(self.cid("KGR"), "DATA_ACCESS")[-1]["metadata"]["decision_matrix"]
        self.note(checks={"VA passes and VL fails": matrix["VA"] is True and matrix["VL"] is False, "nothing is released": got["modules_released"] == []})

    def take_over(self, key, shot_before, shot_after):
        """The take-over on the Patient screen. Returns the record of the re-issue and the rows of the transition."""
        consent_id = self.cid(key)
        if not self.consent(consent_id).successor_id:                 # a continued run does not take over a second time
            self.screens.take_over(self.about["consents"][key]["patient"], self.shot(shot_before), self.shot(shot_after))
        old = self.consent(consent_id)
        if not old.successor_id:
            last = self.rows(consent_id, "CAPACITY_TRANSITION")
            self.keep_shot(shot_after, False, f"the consent {key} was not re-issued: {(last[-1]['metadata'] if last else {}).get('reason')}")
        self.state["consents"][key + "2"] = old.successor_id
        self.save()
        new = self.consent(old.successor_id)
        mint = self.rows(new.consent_id, "ONCHAIN_MINT", "SUCCESS")
        revoke = [e for e in self.rows(consent_id, "ONCHAIN_REVOKE", "SUCCESS") if (e.get("metadata") or {}).get("capacity_transition")]
        transition = self.rows(consent_id, "CAPACITY_TRANSITION")
        for row in mint + revoke:
            self.track(new.consent_id, row["tx_hash"], row["block_number"])
        return old, new, (mint[-1] if mint else None), (revoke[-1] if revoke else None), (transition[-1] if transition else None)

    def s6_13(self):
        from services import revocation_service, state_service
        old, new, mint, revoke, transition = self.take_over("KTR", None, "S6-13_01_patient_took_over")
        refused = len(self.rows(old.consent_id, "REVOKE_CONSENT", "DENIED"))
        self.screens.guardian_revoke(old.consent_id, "did:parent:A", self.shot("S6-13_02_guardian_refused_after_majority"))
        denied = self.rows(old.consent_id, "REVOKE_CONSENT", "DENIED")
        self.keep_shot("S6-13_02_guardian_refused_after_majority", len(denied) > refused,
                       "the revocation requested by the former guardian was not recorded as refused")
        # on the re-issued consent the former guardian is not offered by the screen: the request is made on a copy
        now, ledger, store = self.trusted(), ToolLedger(), self.run_store()
        reissue = self.consent(new.consent_id)
        authority = revocation_service.revocation_authority(reissue, "did:parent:A", now["time"], store)
        signature, _ = revocation_service.sign_revocation("did:parent:A", reissue.consent_id)
        answer = revocation_service.revoke(reissue, "did:parent:A", signature=signature, now=now["time"], time_label=now["source"],
                                           onchain_revoke=revocation_service.NO_CHAIN, audit=ledger, consent_store=store)
        self.service({"called": "revocation_authority, revoke", "on": f"a copy of the record of the re-issued consent KTR2 ({new.consent_id})",
                      "revoker": "did:parent:A", "authority": authority, "result": answer["result"], "reason": answer["reason"],
                      "rows_in_the_ledger_of_the_tool": ledger.rows})
        self.note(outcome="REFUSED" if denied and answer["result"] == "DENIED" else "ACCEPTED",
                  reason=(denied[-1]["metadata"] or {}).get("reason") if denied else None, reason_on_reissue=answer["reason"],
                  successor_state=state_service.lifecycle_state(self.consent(new.consent_id), self.trusted()["time"]),
                  checks={"the transition is recorded": bool(transition) and transition["result"] == "SUCCESS",
                          "the re-issue is minted on chain": bool(mint), "the old token is revoked on chain": bool(revoke),
                          "the refusal records after_majority": bool(denied) and denied[-1]["metadata"].get("after_majority") is True})

    def s6_14(self):
        got = self.denied("K23", scope=["Observation", "Procedure"], after="S6-14_01_clinician_denied_superset")
        held = sorted(self.sealed_copy(self.cid("K23")))
        self.service({"read": "the modules of which the vault of the run holds a sealed copy for K23", "consent": self.cid("K23"),
                      "modules_sealed": held})
        self.note(checks={"the vault holds no copy of Procedure": "Procedure" not in held, "the requested scope is recorded": got["scope"] == ["Observation", "Procedure"]})

    def s6_15(self):
        screen = self.denied("K23", scope=[], after="S6-15_01_clinician_denied_empty_scope")
        forms = {"None": None, "[]": [], "the bare text 'Observation'": "Observation", "a list that holds a number": [1]}
        answers = {name: self.on_copy(self.consent(self.cid("K23")), scope=scope) for name, scope in forms.items()}
        self.service({"called": "submit_request, the request path of the Clinician screen", "on": f"copies of the record of K23 ({self.cid('K23')})",
                      "forms": answers})
        refused = [a for a in [screen] + list(answers.values())
                   if a["outcome"] == "DENIED" and a["deny_code"] == "OUT-OF-SCOPE" and a["failed_checks"] == ["VP"] and not a["modules_released"]]
        self.note(forms_denied=len(refused))

    def s6_16(self):
        self.denied("KPRE", after="S6-16_01_clinician_denied_pre_validity_again")

    def s6_17(self):
        self.past_expiry("KEXP")
        self.denied("KEXP", after="S6-17_01_clinician_denied_expired_again")

    def s6_18(self):
        self.denied("K23", context="GB", after="S6-18_01_clinician_denied_context")

    def s6_19(self):
        got = self.denied("K22", before="S6-19_01_clinician_revoked_before_request", after="S6-19_02_clinician_denied_revoked")
        number = self.token_of("K22")
        valid = self.read("checkValid of the token K22 had", self.token.contract.functions.checkValid(number), token=number)
        self.note(check_valid=valid, checks={"nothing is released": got["modules_released"] == [], "no proof is made": not got["tx_hash"]})

    def retain(self, key):
        """Before a revocation: keep the sealed copy of the consent as the vault file holds it (ciphertext, no key)
        and a copy of its record, which still has the opening of the commitment."""
        consent_id = self.cid(key)
        blobs = self.sealed_copy(consent_id)
        write_json(self.path("app", "retained", f"{key}.json"), blobs)
        write_json(self.path("app", "snapshots", f"{key}_record_before_revocation.json"), self.record(consent_id))
        self.state["kept"].setdefault("retained", {})[key] = sorted(blobs)
        self.save()
        return blobs

    def retained(self, key):
        path = self.path("app", "retained", f"{key}.json")
        if not os.path.exists(path):
            raise NotRun(f"no copy of the ciphertext of {key} was kept before its revocation")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def kept_record(self, key):
        from models.consent import Consent
        path = self.path("app", "snapshots", f"{key}_record_before_revocation.json")
        if not os.path.exists(path):
            raise NotRun(f"no copy of the record of {key} was kept before its revocation")
        with open(path, encoding="utf-8") as f:
            row = json.load(f)
        return Consent(**{name: value for name, value in row.items() if name in Consent.__dataclass_fields__})

    def patient_revoke(self, key, shot_before, shot_after):
        """The patient's Revoke on the screen. Returns the REVOKE_CONSENT and ONCHAIN_REVOKE rows and the two roots."""
        consent_id, number = self.cid(key), self.token_of(key)
        if not self.record(consent_id)["revoked"]:                    # a continued run does not revoke a second time
            self.state["kept"][f"root_before_{key}"] = str(self.token.revocation_root())
            self.save()
            self.screens.patient_revoke(self.about["consents"]["L" if key == "L2" else key]["patient"], consent_id,
                                        self.shot(shot_before), self.shot(shot_after))
            self.keep_shot(shot_after, bool(self.record(consent_id)["revoked"]), f"the patient's revocation of {key} was not recorded")
        revoke, onchain = self.revocation_rows(key)
        if onchain and onchain.get("tx_hash"):
            self.track(consent_id, onchain["tx_hash"], onchain["block_number"])
        return revoke, onchain, self.state["kept"].get(f"root_before_{key}"), str(self.token.revocation_root()), number

    def s6_20(self):
        from web3.logs import DISCARD
        self.retain("K22")
        revoke, onchain, root_before, root_after, number = self.patient_revoke(
            "K22", "S6-20_01_patient_my_consents_before", "S6-20_02_patient_revoked_onchain")
        m = (revoke or {}).get("metadata") or {}
        event, logs, status = None, None, None
        if onchain and onchain.get("tx_hash"):
            receipt = self.w3.eth.get_transaction_receipt(onchain["tx_hash"])
            found = self.token.contract.events.ConsentRevoked().process_receipt(receipt, errors=DISCARD)
            logs, status = len(receipt["logs"]), int(receipt["status"])
            if len(found) == 1 and dict(found[0]["args"]) == {"tokenId": number}:
                event = "ConsentRevoked(tokenId)"
        valid = self.read("checkValid after the revocation", self.token.contract.functions.checkValid(number), token=number,
                          revocation_root_before=str(root_before), revocation_root_after=str(root_after))
        self.note(outcome=m.get("revocation") if revoke and revoke["result"] == "SUCCESS" else "REFUSED",
                  revoker_role=m.get("revoker_role"), onchain_revoke=(onchain or {}).get("result"), event=event, check_valid=valid,
                  complete=m.get("complete"),
                  checks={"the receipt has status 1 and one log": status == 1 and logs == 1,
                          "the revocation root has changed": root_before != root_after,
                          "the record holds the new root": str((onchain or {}).get("metadata", {}).get("revocation_root")) == str(root_after)})

    def revocation_evidence(self, key, retained=None):
        """The deletion, unintelligibility and notification tests of a revoked consent, against the stores of the run."""
        from services import revocation_service
        consent = self.consent(self.cid(key))
        return revocation_service.revocation_evidence(consent, vault=self.read_only_vault(), audit=self.run_ledger(),
                                                      retained_copy=retained, consent_store=self.run_store())

    def s6_21(self):
        consent_id = self.cid("K22")
        evidence, copies, keys = self.revocation_evidence("K22"), self.sealed_copy(consent_id), self.key_references(consent_id)
        destroyed = self.destruction_record(consent_id)
        record = self.record(consent_id)
        self.service({"read": "the vault file, the key store file and the record of K22, after the revocation", "consent": consent_id,
                      "modules_in_the_vault": sorted(copies), "key_references_in_the_key_store": keys,
                      "destruction_record": destroyed, "revocation_evidence": evidence,
                      "record_fields": {name: record.get(name) for name in ("commitment_opening", "commitment", "token_id", "token_address")}})
        self.note(outcome="PASS" if evidence["deletion"] and not copies and not keys else "FAIL", deletion=evidence["deletion"],
                  copies_remaining=len(copies), keys_remaining=len(keys), link_deleted=evidence["link_deleted"],
                  checks={"the destruction of the keys is recorded": bool(destroyed) and bool(destroyed.get("key_ids"))})

    def s6_22(self):
        from services import key_store
        retained = self.retained("K22")
        keys, opened, answers = self.read_only_vault().key_store, [], {}
        for module, blob in retained.items():
            try:
                keys.decrypt(blob["consent_id"], blob["module"], bytes.fromhex(blob["nonce"]), bytes.fromhex(blob["ciphertext"]))
                opened.append(module)
                answers[module] = "OPENED"
            except key_store.KeyStoreError as error:
                answers[module] = f"{type(error).__name__}: {error}"
        evidence = self.revocation_evidence("K22", retained)
        self.service({"called": "KeyStore.decrypt for every blob kept from before the revocation, revocation_evidence",
                      "consent": self.cid("K22"), "blobs_kept": sorted(retained), "answer_of_the_key_store": answers,
                      "revocation_evidence": evidence})
        self.note(outcome="REFUSED" if retained and not opened else "OPENED", unintelligibility=evidence["unintelligibility"],
                  retained_blobs_opened=evidence["retained_blobs_opened"],
                  checks={"a copy of the ciphertext was kept": len(retained) > 0, "no blob opens": opened == []})

    def notified(self, key, shot, replaced=()):
        from services import notification_service
        consent_id = self.cid(key)
        check = notification_service.notification_check(consent_id, self.run_ledger(), consent_ids=[self.cid(k) for k in replaced])
        notices = self.rows(consent_id, "WITHDRAWAL_NOTIFICATION", "SENT")
        self.screens.notices(consent_id, CLINICIAN, self.shot(shot))
        self.service({"called": "notification_check", "consent": consent_id, "with_the_consent_it_replaced": [self.cid(k) for k in replaced],
                      "answer": check, "notices": [dict(e["metadata"], modules=e["scope"]) for e in notices]})
        return check, notices

    def s6_23(self):
        check, notices = self.notified("K22", "S6-23_01_clinician_notice")
        m = notices[-1]["metadata"] if notices else {}
        self.note(outcome="PASS" if check["complete"] and notices else "FAIL", notification=check["complete"],
                  recipients=check["recipients"], missing=check["missing"],
                  checks={"one notice names the recipient": len(notices) == 1 and m.get("recipient_did") == CLINICIAN,
                          "it names the two releases": m.get("releases") == 2,
                          "it names the modules received": sorted(notices[-1]["scope"] or []) == ["Medication", "Observation"] if notices else False})

    # ---- the scenarios of Chapter 7 -----------------------------------------------------------------------
    def verification(self, tx_hash):
        """The transaction of a verification: its receipt, its ConsentVerified event, and the proof read back."""
        from web3.logs import DISCARD
        receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        events = self.verifier.contract.events.ConsentVerified().process_receipt(receipt, errors=DISCARD)
        event = {k: (v if isinstance(v, bool) else str(v)) for k, v in dict(events[0]["args"]).items()} if events else {}
        submitted = self.verifier.submitted_proof(tx_hash)
        return receipt, event, submitted

    def s7_01(self):
        from services import commitment_service
        got = self.request("K22", scope=["Medication"], after="S7-01_01_clinician_granted_proof_on_chain")
        if not got["tx_hash"]:
            raise RuntimeError(f"the request was {got['outcome']} and has no verification transaction")
        receipt, event, submitted = self.verification(got["tx_hash"])
        again = self.verifier.reverify(submitted["proof"], submitted["publicSignals"])
        self.calls.append({"scenario": self.current, "call": "the proof read back from the transaction, verified again",
                           "function": "verifyProof", "from": None, "block": self.w3.eth.block_number, "refused": not again,
                           "reason": None, "answer": again, "tx_hash": got["tx_hash"], "event": event})
        write_json(self.path("chain", "calls.json"), self.calls)
        self.evidence("chain/calls.json")
        to_requester = commitment_service.open_tag(got["tag"], CLINICIAN, got["nonce"])
        to_other = commitment_service.open_tag(got["tag"], REGISTRAR, got["nonce"])
        self.service({"called": "open_tag", "tag": got["tag"], "with_the_requester_of_the_row": to_requester,
                      "with_another_clinician": to_other, "verification": got["tx_hash"], "event": event})
        self.state["kept"]["S7-01_tx"] = got["tx_hash"]
        self.note(outcome=got["outcome"], deny_code=got["deny_code"], accepted=int(receipt["status"]) == 1 and event.get("result") is True,
                  reverified=again, tag_opens_to_requester=to_requester, tag_opens_to_other=to_other,
                  checks={"the event carries the public inputs and the result only":
                              set(event) == {"tag", "t", "role", "purpose", "context", "consentRoot", "revocationRoot", "result"},
                          "the modules released are the requested ones": got["modules_released"] == ["Medication"]})

    def unprovable(self, consent, what, **request):
        answer = self.no_proof(consent, **request)
        self.service({"called": "build_statement, prove_decision (with and without the statement check)", "on": what, **answer})
        self.note(outcome="NO PROOF" if not answer["proof_made"] else "A PROOF WAS MADE", failed_predicates=answer["failed_predicates"],
                  circuit_refused=answer["circuit_refused"])
        return answer

    def s7_02(self):
        self.past_expiry("KEXP")
        self.unprovable(self.consent(self.cid("KEXP")), "a copy of the record of KEXP after its expiry", scope=["Observation"])

    def s7_03(self):
        kept = self.kept_record("K22")
        answer = self.unprovable(kept, "the record of K22 kept from before the revocation, with its opening", scope=["Observation"])
        now = self.no_proof(self.consent(self.cid("K22")), scope=["Observation"])
        self.service({"called": "build_statement, prove_decision", "with_the_record_kept_from_before": answer,
                      "with_the_record_as_it_is_now": now})
        self.note(failed_predicates_now=now["failed_predicates"], checks={"no proof from the record as it is now": not now["proof_made"]})

    def s7_04(self):
        self.unprovable(self.consent(self.cid("K22")), "a copy of the record of K22, the requester claiming the role guardian",
                        role="guardian", scope=["Observation"])

    def s7_05(self):
        self.unprovable(self.consent(self.cid("K22")), "a copy of the record of K22, purpose Research", purpose="Research",
                        scope=["Observation"])

    def s7_06(self):
        self.unprovable(self.consent(self.cid("K22")), "a copy of the record of K22, requester did:hospital:002",
                        requester_did=REGISTRAR, scope=["Observation"])

    def s7_07(self):
        proof = self.prove(self.consent(self.cid("K22")), scope=["Observation"])
        signals = list(proof["publicSignals"])
        signals[2] = "2" if signals[2] == "1" else "1"
        first = self.present("the proof with its purpose signal changed", proof, signals)
        bent = copy.deepcopy(proof)
        bent["proof"]["pi_a"][0] = str(int(bent["proof"]["pi_a"][0]) + 1)
        second = self.present("the proof with one coordinate of its first point changed", bent)
        seen = self.verifier.tag_seen(int(proof["tag"]))
        self.service({"called": "prove_decision for a request of did:hospital:001 on K22 (not submitted)", "tag": proof["tag"],
                      "public_signals": proof["publicSignals"], "calls": [first, second], "tag_seen_afterwards": seen})
        refused = [c for c in (first, second) if c["refused"]]
        self.note(outcome="REJECTED" if len(refused) == 2 else "ACCEPTED", reason_text=first["reason"], calls_refused=len(refused),
                  checks={"both calls give the same reason": first["reason"] == second["reason"], "the tag stays unseen": seen is False})

    def s7_08(self):
        tx_hash = self.state["kept"].get("S7-01_tx")
        if not tx_hash:
            raise NotRun("the accepted proof of S7-01 is missing")
        submitted = self.verifier.submitted_proof(tx_hash)
        answer = self.present("the accepted proof of S7-01, presented a second time", submitted["proof"], submitted["publicSignals"])
        self.note(outcome="REJECTED" if answer["refused"] else "ACCEPTED", reason_text=answer["reason"])

    def s7_09(self):
        consent = self.consent(self.cid("K22"))
        self.move_time(datetime.fromisoformat(consent.start_date) + timedelta(seconds=305), "the consent K22 has existed for 301 seconds")
        back = self.trusted()["unix"] - 301
        proof = self.prove(consent, scope=["Observation"], now_ts=back)
        answer = self.present("a proof whose time is 301 seconds before the latest block", proof)
        self.service({"called": "prove_decision with the time of the latest block minus 301 seconds", "t": back,
                      "public_signals": proof["publicSignals"], "call": answer})
        self.note(outcome="REJECTED" if answer["refused"] else "ACCEPTED", reason_text=answer["reason"])

    def s7_10_keep(self):
        proof = self.prove(self.consent(self.cid("K22")), scope=["Observation"])
        self.state["kept"]["S7-10"] = proof
        self.note(checks={"a valid proof was built before the revocation": bool(proof.get("proof"))})

    def s7_10_present(self):
        proof = self.state["kept"].get("S7-10")
        if not proof:
            raise NotRun("the proof that was to be built before the revocation of S6-02 is missing")
        answer = self.present("the proof built before the revocation of KGR, presented after it", proof)
        on_chain = str(self.token.revocation_root())
        self.service({"called": "prove_decision before the revocation of S6-02 (not submitted)", "public_signals": proof["publicSignals"],
                      "revocation_root_in_the_proof": proof["publicSignals"][6], "revocation_root_on_chain": on_chain, "call": answer})
        self.note(outcome="REJECTED" if answer["refused"] else "ACCEPTED", reason_text=answer["reason"],
                  checks={"the root of the proof is not the root on chain": str(proof["publicSignals"][6]) != on_chain})

    def s7_11(self):
        self.past_expiry("KEXP")
        answer = self.no_proof(self.consent(self.cid("KEXP")), scope=["Observation"])
        self.service({"called": "prove_decision without the statement check: the witness goes to the circuit",
                      "on": "a copy of the record of KEXP after its expiry", **answer})
        self.note(outcome="NO PROOF" if not answer["proof_made"] else "A PROOF WAS MADE", failed_predicates=answer["failed_predicates"],
                  circuit_refused=answer["circuit_refused"])

    # ---- the case study -------------------------------------------------------------------------------------
    def cs_01(self):
        from services import state_service
        self.create("L", "CS-01_01_patient_form", "CS-01_02_patient_created")
        record = self.consent(self.cid("L"))
        scheduled = self.rows(self.cid("L"), "SCHEDULE_TRANSITION")
        self.note(outcome="CREATED", state=state_service.lifecycle_state(record, self.trusted()["time"]),
                  transition_scheduled=bool(scheduled) and bool(record.transitions),
                  checks={"the record holds a commitment": bool(record.commitment), "nothing is on chain yet": not record.token_id})

    def cs_02(self):
        from services import access_service, state_service
        self.approve("L", "did:parent:A", "CS-02_01_guardian_faisal_1of2")
        record = self.consent(self.cid("L"))
        write_json(self.path("app", "snapshots", "L_record_at_1_of_2.json"), self.record(self.cid("L")))
        self.note(outcome="PENDING" if not record.token_id else "ISSUED",
                  approvals=f"{len(access_service.guardian_approvals(record))}/{record.threshold}",
                  state=state_service.lifecycle_state(record, self.trusted()["time"]),
                  checks={"the identity of the guardian was verified": bool(self.rows(self.cid("L"), "IDENTITY_VERIFICATION", "VALID"))})

    def cs_03(self):
        from web3.logs import DISCARD
        self.approve("L", "did:parent:B", "CS-03_01_guardian_huda_2of2_token")
        mint = self.anchored("L", "CS-03_02_guardian_anchored")
        record = self.issued("L")
        receipt = self.w3.eth.get_transaction_receipt(mint["tx_hash"])
        issued = self.token.contract.events.ConsentIssued().process_receipt(receipt, errors=DISCARD)
        token = self.token_of("L")
        stored = self.read("consents(token) of Layan's consent", self.token.contract.functions.consents(token), token=token)
        self.note(checks={"the event carries the token and the commitment": len(issued) == 1 and
                          dict(issued[0]["args"]) == {"tokenId": token, "commitment": int(record.commitment, 16)},
                          "the token stores the commitment and the revocation state": list(stored) == [int(record.commitment, 16), False]})

    def cs_04(self):
        from models.consent import Consent
        from services import identity_service
        offered = self.screens.guardian_options(self.cid("L"), self.shot("CS-04_01_guardian_selector_without_uncle"))
        uncle = identity_service.verify_identity("did:parent:C", role="guardian")
        path = self.path("app", "snapshots", "L_record_at_1_of_2.json")
        if not os.path.exists(path):
            raise NotRun("the copy of Layan's consent at 1 of 2 (CS-02) is missing")
        with open(path, encoding="utf-8") as f:
            row = json.load(f)
        answer = self.outside_signer(Consent(**{k: v for k, v in row.items() if k in Consent.__dataclass_fields__}), "did:parent:C")
        self.service({"called": "verify_identity, sign_consent_v2, guardian_approvals, threshold_met, lifecycle_state, submit_request",
                      "on": "the copy of the record of Layan's consent kept at 1 of 2", "selector_offers": offered,
                      "uncle_identity": uncle.as_dict(), **answer})
        self.note(outcome="REFUSED" if answer["decision"]["outcome"] == "DENIED" and not answer["threshold_met"] else "ACCEPTED",
                  uncle_identity=uncle.result, approvals_counted=answer["approvals_counted"], threshold_met=answer["threshold_met"],
                  deny_code=answer["decision"]["deny_code"],
                  checks={"the selector offers the two parents only": offered == ["did:parent:A", "did:parent:B"],
                          "the request on the copy fails VA and VL": answer["decision"]["failed_checks"] == ["VA", "VL"]})

    def cs_05(self):
        got = self.request("L", scope=["Observation", "Medication"], before="CS-05_01_clinician_matrix_all_pass",
                           after="CS-05_02_clinician_granted_two_modules")
        event = self.verification(got["tx_hash"])[1] if got["tx_hash"] else {}
        self.note(outcome=got["outcome"], deny_code=got["deny_code"], failed_checks=got["failed_checks"],
                  modules_released=got["modules_released"], proof_verified=got["proof_verified"],
                  checks={"the time is the block timestamp": got["time_source"] == "block-timestamp",
                          "the proof was verified on chain": event.get("result") is True})

    def cs_06(self):
        got = self.denied("L", requester=REGISTRAR, purpose="Research", scope=["Procedure"],
                          before="CS-06_01_clinician_registrar_vi_failed", after="CS-06_02_clinician_registrar_denied")
        self.note(checks={"the row names the registrar and the request": (got["requester"], got["scope"], got["purpose"]) ==
                          (REGISTRAR, ["Procedure"], "Research"), "nothing is released": got["modules_released"] == []})

    def cs_07(self):
        from services import state_service
        old, new, mint, revoke, transition = self.take_over("L", "CS-07_01_patient_majority_reached", "CS-07_02_patient_reissued_on_chain")
        executed = ((transition or {}).get("metadata") or {}).get("executed_at") or self.trusted()["time"].isoformat()
        self.state["kept"]["transition_day"] = datetime.fromisoformat(executed).date().isoformat()
        self.save()
        old_token, new_token = self.token_of("L"), self.token_of("L2")
        old_valid = self.read("checkValid of the old token", self.token.contract.functions.checkValid(old_token), token=old_token)
        new_valid = self.read("checkValid of the new token", self.token.contract.functions.checkValid(new_token), token=new_token)
        self.note(outcome="COMPLETED" if transition and transition["result"] == "SUCCESS" else (transition or {}).get("result"),
                  successor_guardians=new.guardian_dids, successor_threshold=new.threshold, old_token_valid=old_valid,
                  new_token_valid=new_valid, successor_state=state_service.lifecycle_state(new, self.trusted()["time"]),
                  checks={"the re-issue is signed by the patient over its commitment":
                              (new.signature_data.get(new.patient_did) or {}).get("version") == 2 and bool(new.commitment),
                          "one mint and one revocation on chain": bool(mint) and bool(revoke),
                          "the old consent names its successor": old.successor_id == new.consent_id and old.revoked})

    def cs_08(self):
        got = self.request("L2", scope=["Observation", "Medication"], after="CS-08_01_clinician_granted_reissued")
        day = datetime.fromisoformat(got["decision_time"]).date().isoformat() if got["decision_time"] else None
        transition_day = self.state["kept"].get("transition_day")
        self.state["kept"]["CS-08_tx"] = got["tx_hash"]
        self.note(outcome=got["outcome"], deny_code=got["deny_code"], failed_checks=got["failed_checks"],
                  modules_released=got["modules_released"], following_day=bool(day and transition_day and day > transition_day),
                  day_of_the_transition=transition_day, day_of_the_request=day,
                  checks={"the proof was verified on chain": bool(got["tx_hash"])})

    def cs_09(self):
        retained = {f"{key}:{module}": blob for key in ("L", "L2") for module, blob in self.retain(key).items()}
        kept = self.prove(self.consent(self.cid("L2")), scope=["Observation"])
        revoke, onchain, root_before, root_after, number = self.patient_revoke(
            "L2", "CS-09_01_patient_my_consents_before", "CS-09_02_patient_revoked_keys_destroyed")
        presented = self.present("the proof built before Layan's revocation, presented at once after it", kept)
        self.state["kept"]["CS-09_presented"] = presented
        evidence = self.revocation_evidence("L2", retained)
        m = (revoke or {}).get("metadata") or {}
        self.service({"called": "revocation_evidence with the copies of the ciphertext kept from before",
                      "consents": {"L": self.cid("L"), "L2": self.cid("L2")}, "blobs_kept": sorted(retained),
                      "revocation_evidence": evidence, "proof_kept_from_before_presented_after": presented})
        self.note(outcome=m.get("revocation") if revoke and revoke["result"] == "SUCCESS" else "REFUSED",
                  revoker_role=m.get("revoker_role"), deletion=evidence["deletion"], unintelligibility=evidence["unintelligibility"],
                  link_deleted=evidence["link_deleted"], onchain_revoke=(onchain or {}).get("result"),
                  checks={"copies of both consents were kept from before": len(retained) >= 2 and evidence["retained_blobs_tested"] == len(retained),
                          "no kept blob opens": evidence["retained_blobs_opened"] == [],
                          "the token is not valid any more": self.token.check_valid(number) is False,
                          "the revocation root has changed": root_before != root_after})

    def cs_10(self):
        check, notices = self.notified("L2", "CS-10_01_clinician_notice", replaced=("L",))
        m = notices[-1]["metadata"] if notices else {}
        self.note(outcome="PASS" if check["complete"] and notices else "FAIL", notification=check["complete"],
                  recipients=check["recipients"], releases=m.get("releases"), missing=check["missing"],
                  checks={"the registrar is not a recipient": REGISTRAR not in check["recipients"],
                          "the data was received under both consents": sorted(m.get("received_under") or []) == sorted([self.cid("L"), self.cid("L2")]),
                          "the notice says that delivered data is not recalled": "not recalled" in (m.get("message") or "")})

    def cs_11(self):
        got = self.denied("L2", before="CS-11_01_clinician_revoked_before_request", after="CS-11_02_clinician_denied_revoked")
        self.note(checks={"nothing is released": got["modules_released"] == []})

    def cs_12(self):
        new = self.no_proof(self.kept_record("L2"), scope=["Observation"])
        presented = self.state["kept"].get("CS-09_presented")
        tx_hash = self.state["kept"].get("CS-08_tx")
        if not presented or not tx_hash:
            raise NotRun("the proof kept in CS-09 or the accepted proof of CS-08 is missing")
        submitted = self.verifier.submitted_proof(tx_hash)
        replay = self.present("the accepted proof of CS-08, presented again", submitted["proof"], submitted["publicSignals"])
        signals = list(submitted["publicSignals"])
        signals[2] = 2 if int(signals[2]) == 1 else 1
        tampered = self.present("the accepted proof of CS-08 with one public signal changed", submitted["proof"], signals)
        self.service({"called": "prove_decision with the record of L2 kept from before the revocation", "new_proof": new,
                      "proof_built_before_the_revocation": presented, "replayed": replay, "tampered": tampered})
        refused = [c for c in (presented, replay, tampered) if c["refused"]]
        self.note(outcome="REJECTED" if len(refused) == 3 and not new["proof_made"] else "ACCEPTED",
                  new_proof="NO PROOF" if not new["proof_made"] else "A PROOF WAS MADE", calls_refused=len(refused),
                  checks={"the new proof fails on NOT_REVOKED": new["failed_predicates"] == ["NOT_REVOKED"],
                          "the proof built before is refused on the revocation root": presented["reason"] == "revocation root is not current",
                          "the replayed proof is refused on its tag": replay["reason"] == "tag already seen",
                          "the tampered copy is refused on its tag": tampered["reason"] == "tag already seen"})

    def cs_13(self):
        self.screens.audit(self.cid("L"), self.shot("CS-13_01_auditor_lifecycle_L"))
        self.screens.audit(self.cid("L2"), self.shot("CS-13_02_auditor_lifecycle_L2"))
        self.screens.p.get_by_text("Audit Ledger - local events", exact=False).scroll_into_view_if_needed()
        self.screens.shot(self.shot("CS-13_03_auditor_ledger"))
        code, text = self.verify_poc()
        last = [line for line in text.splitlines() if line.startswith("RESULT: ")]
        self.note(outcome=last[-1][8:] if last else "NO RESULT", exit_code=code)
        self.state["verified_rows"] = len(self.ledger())       # the rows of the ledger that this verification covers
        self.evidence("verification/verify_poc.txt")
        self.evidence("ledger/audit_ledger.json")
        self.evidence("ledger/case_study.json")

    # ---- the order of the run ---------------------------------------------------------------------------------
    # (scenario, the part of it, the function). A scenario is judged when its last part of the list has run.
    STAGES = {
        1: [("S5-01", "", "s5_01"), ("S5-02", "", "s5_02"), ("S5-03", "", "s5_03"), ("S5-04", "", "s5_04"), ("S5-05", "", "s5_05"),
            ("S5-06", "", "s5_06"), ("S5-07", "", "s5_07"), ("S5-08", "", "s5_08"), ("S5-09", "", "s5_09"), ("S5-10", "", "s5_10"),
            ("S5-11", "", "s5_11"), ("S6-08", "creation, issue and the request inside the window", "s6_08_issue"),
            ("S6-09", "creation and one approval", "s6_09_create"), ("S6-07", "", "s6_07"), ("S6-16", "", "s6_16"),
            ("S6-01", "", "s6_01"), ("S7-01", "", "s7_01"), ("S6-03", "", "s6_03"), ("S6-04", "", "s6_04"), ("S6-05", "", "s6_05"),
            ("S6-06", "", "s6_06"), ("S6-14", "", "s6_14"), ("S6-15", "", "s6_15"), ("S6-18", "", "s6_18"), ("S7-04", "", "s7_04"),
            ("S7-05", "", "s7_05"), ("S7-06", "", "s7_06"), ("S7-07", "", "s7_07"), ("S7-08", "", "s7_08"), ("S7-09", "", "s7_09"),
            ("S6-02", "creation, issue and the granted request", "s6_02_issue"), ("S7-10", "the kept proof", "s7_10_keep"),
            ("S6-02", "the guardian's revocation", "s6_02_revoke"), ("S7-10", "the kept proof presented", "s7_10_present"),
            ("S6-12", "", "s6_12"), ("S6-10", "", "s6_10"), ("S6-11", "creation and the request the day before", "s6_11_day_before"),
            ("S6-08", "after the expiry", "s6_08_expired"), ("S6-09", "after the expiry", "s6_09_expired"), ("S6-17", "", "s6_17"),
            ("S7-02", "", "s7_02"), ("S7-11", "", "s7_11"), ("S6-20", "", "s6_20"), ("S6-21", "", "s6_21"), ("S6-22", "", "s6_22"),
            ("S6-23", "", "s6_23"), ("S6-19", "", "s6_19"), ("S7-03", "", "s7_03"), ("CS-01", "", "cs_01"), ("CS-02", "", "cs_02"),
            ("CS-03", "", "cs_03"), ("CS-04", "", "cs_04"), ("CS-05", "", "cs_05"), ("CS-06", "", "cs_06")],
        2: [("S6-11", "the request after midnight", "s6_11_majority"), ("S6-13", "", "s6_13"), ("CS-07", "", "cs_07")],
        3: [("CS-08", "", "cs_08"), ("CS-09", "", "cs_09"), ("CS-10", "", "cs_10"), ("CS-11", "", "cs_11"), ("CS-12", "", "cs_12")],
        "close": [("CS-13", "", "cs_13")],
    }

    def last_part(self, scenario_id):
        parts = [(stage, part) for stage, steps in self.STAGES.items() for sid, part, _ in steps if sid == scenario_id]
        return parts[-1] if parts else None

    def run_part(self, stage, scenario_id, part, function):
        """One part of one scenario. Whatever happens in it is recorded with the scenario, and the run goes on."""
        key = f"{scenario_id}:{part}"
        result = self.state["results"].setdefault(scenario_id, {})
        if key in self.state["done"] or result.get("result") == NOT_RUN:
            return
        if result.get("result") == ERROR and result.get("failed_part") != key:
            return                                 # an earlier part of this scenario failed in this run
        again = result.get("message") if result.get("result") == ERROR else None
        result.pop("result", None)
        self.current = scenario_id
        self.say(f"  {scenario_id}{' (' + part + ')' if part else ''}: {self.scenarios[scenario_id]['what']}")
        ledger = self.ledger()
        before = {e["event_id"] for e in ledger}
        # The rows that an attempt of a part added before it broke off are kept by part: a step of that attempt
        # which the ledger holds is not made a second time. An attempt that ended with the tool (the tool was
        # stopped while the part ran) left its mark in the state: its rows are those the ledger gained since.
        kept = self.state.setdefault("attempts", {})
        cut = self.state.pop("running", None)
        if cut:
            rows = [e["event_id"] for e in ledger[cut.get("rows", len(ledger)):]]
            for known in (kept.setdefault(cut["part"], []), self.state["added"].setdefault(cut["part"].split(":", 1)[0], [])):
                known.extend(i for i in rows if i not in known)
            self.state.setdefault("cut_off", []).append(cut["part"])
        if key in self.state.get("cut_off", []):
            self.state["cut_off"].remove(key)
            again = again or "the tool was stopped while it ran"
        attempts = kept.setdefault(key, [])
        self.earlier, self.reused = set(attempts), set()
        if again:
            self.remark(f"{'the part ' + repr(part) if part else 'the scenario'} was run again after an attempt that broke off ({again})")
        self.state["running"] = {"part": key, "rows": len(ledger)}
        self.save()
        try:
            getattr(self, function)()
            self.state["done"].append(key)
            result.pop("failed_part", None)
            result.pop("message", None)
            if (stage, part) == self.last_part(scenario_id):
                result["observed"] = self.state["observed"].get(scenario_id, {})
                result["result"], result["differences"] = compare(self.scenarios[scenario_id], result["observed"])
        except NotRun as reason:
            result.update(result=NOT_RUN, message=str(reason))
        except Exception as error:
            result.update(result=ERROR, failed_part=key, message=f"{type(error).__name__}: {str(error).splitlines()[0][:300]}",
                          observed=self.state["observed"].get(scenario_id, {}))
            with open(self.path("errors.log"), "a", encoding="utf-8") as f:
                f.write(f"\n{datetime.now().isoformat(timespec='seconds')} {key}\n{traceback.format_exc()}")
            try:
                self.screens.p.screenshot(path=self.path("screens", f"{scenario_id}_error.png"), full_page=True)
                self.evidence(f"screens/{scenario_id}_error.png")
            except Exception:
                pass
        added = [e["event_id"] for e in self.ledger() if e["event_id"] not in before]
        self.state["added"].setdefault(scenario_id, []).extend(added)
        if result.get("result") == ERROR:
            attempts.extend(added)
        self.state.pop("running", None)
        self.say(f"    -> {result.get('result') or 'part done'}" + (f": {result.get('message') or '; '.join(result.get('differences') or [])}"
                                                                     if result.get("result") in (FAIL, ERROR, NOT_RUN) else ""))
        self.save()
        write_summary(os.path.join(self.out, "summary"), [self.scenarios[i] for i in self.order], self.state["results"])

    def stage_done(self, stage):
        return all(f"{sid}:{part}" in self.state["done"] or self.state["results"].get(sid, {}).get("result") in (NOT_RUN, ERROR)
                   for sid, part, _ in self.STAGES[stage])

    def due_stage(self):
        """The first stage that has not ended, or "close" when the three stages have."""
        for stage in (1, 2, 3):
            if not self.state["stages"].get(str(stage), {}).get("ended"):
                return stage
        return "close"

    def prepare_stage(self, stage, same_day=False):
        """Check that the time of the chain allows the stage. On a chain whose time can be moved, move it."""
        now = self.trusted()["time"]
        if stage == 1 and not self.state["stages"].get("1"):
            midnight = next_midnight(now)
            if midnight - now < timedelta(minutes=MIN_BEFORE_MIDNIGHT):
                if self.sepolia:
                    raise Stop(f"Less than {MIN_BEFORE_MIDNIGHT} minutes remain before midnight ({now:%Y-%m-%d %H:%M} by the time of "
                               "the chain, in the time zone of this machine). Stage 1 must end before it: start it after midnight.")
                self.move_time(midnight + timedelta(minutes=5), "stage 1 starts after midnight, so that it ends on one day")
        if stage == 2:
            due = []
            for key in ("KTR", "L"):
                if key in self.state["consents"]:
                    due += [datetime.fromisoformat(t["due"]) for t in (self.record(self.state["consents"][key]) or {}).get("transitions", [])]
            if due and now < max(due):
                if self.sepolia:
                    raise Stop(f"Stage 2 is due after {max(due):%Y-%m-%d %H:%M} (time zone of this machine): on that day the two "
                               f"consents of the transition pass to the patients. The time of the chain is {now:%Y-%m-%d %H:%M}. "
                               "Start the tool again after it.")
                self.move_time(max(due) + timedelta(minutes=5), "the day of majority begins")
        if stage == 3 and not same_day:
            day = self.state["kept"].get("transition_day")
            if day and now.date().isoformat() <= day:
                after = next_midnight(now)
                if self.sepolia:
                    raise Stop(f"Stage 3 is due after {after:%Y-%m-%d %H:%M} (time zone of this machine), the day after the transition. "
                               "Start the tool again after it. For a trial, --same-day runs the stage now, and CS-08 is then "
                               "recorded as failed, because its request is not made on the following day.")
                self.move_time(after + timedelta(minutes=5), "the following day begins")

    def run_stage(self, stage, only=None, same_day=False):
        self.prepare_stage(stage, same_day)
        mark = self.state["stages"].setdefault(str(stage), {})
        mark.setdefault("started", datetime.now().isoformat(timespec="seconds"))
        self.say(f"Stage {stage}")
        for scenario_id, part, function in self.STAGES[stage]:
            if only and scenario_id not in only:
                continue
            self.run_part(stage, scenario_id, part, function)
        if not only and self.stage_done(stage):
            mark["ended"] = datetime.now().isoformat(timespec="seconds")
        self.save()

    # ---- the closing evidence ---------------------------------------------------------------------------------
    def verify_poc(self):
        """Run the independent verification tool on the database of the run, in a process that holds no key."""
        environment = child_environment(os.environ)
        environment.update({name: os.environ[name] for name in ("RPC_URL", "CONTRACT_V4_ADDRESS", "VERIFIER_ADDRESS", "CHAIN_ID")
                            if os.environ.get(name)})
        environment["HALAH_DB_PATH"] = self.db
        done = subprocess.run([sys.executable, "-m", "tools.verify_poc"], cwd=REPO, env=environment, capture_output=True,
                              text=True, timeout=1800)
        text = done.stdout + f"\nexit code {done.returncode}\n"
        with open(self.path("verification", "verify_poc.txt"), "w", encoding="utf-8") as f:
            f.write(text)
        if done.returncode not in (0, 1):
            with open(self.path("verification", "verify_poc_errors.txt"), "w", encoding="utf-8") as f:
                f.write(done.stderr)
        return done.returncode, text

    def keys_of_consents(self):
        return {consent_id: key for key, consent_id in self.state["consents"].items()}

    def scenario_of(self):
        return {event_id: sid for sid, events in self.state["added"].items() for event_id in events}

    def export_ledger(self):
        ledger = self.ledger()
        write_json(self.path("ledger", "audit_ledger.json"), ledger)
        columns = ["timestamp", "action", "actor_role", "onchain", "tx_hash", "block_number", "consent_id", "result", "event_id",
                   "actor_did", "patient_did", "scope", "purpose", "metadata", "event_digest"]
        write_csv(self.path("ledger", "audit_ledger.csv"), columns,
                  [dict(e, scope=json.dumps(e.get("scope")), metadata=json.dumps(e.get("metadata"), default=str)) for e in ledger])
        by_id = {e["event_id"]: e for e in ledger}
        for sid, events in self.state["added"].items():
            write_json(self.path("ledger", "by_scenario", f"{sid}.json"), [by_id[i] for i in events if i in by_id])
        case = [self.state["consents"].get(key) for key in ("L", "L2")]
        write_json(self.path("ledger", "case_study.json"), [e for e in ledger if e.get("consent_id") in case and e.get("consent_id")])
        return ledger

    def export_chain(self, ledger):
        """The contracts, the receipt of every transaction of the ledger and of every proof reference, their events,
        and the links."""
        from web3.logs import DISCARD
        w3, keys, scenario_of = self.w3, self.keys_of_consents(), self.scenario_of()
        groth16 = self.verifier.contract.functions.proofVerifier().call()
        poseidon = self.token.contract.functions.hasher().call()
        contracts = [
            {"contract": "ConsentSBTv4", "address": self.token.address, "owner": self.token.contract.functions.owner().call(),
             "hasher": poseidon, "consent_count": self.token.consent_count(), "deploy_block": os.environ.get("CONTRACT_V4_DEPLOY_BLOCK")},
            {"contract": "PoseidonT3", "address": poseidon},
            {"contract": "Groth16Verifier (HalahDecisionVerifier)", "address": groth16},
            {"contract": "ConsentDecisionVerifier", "address": self.verifier.address, "proof_verifier": groth16,
             "consent_token": self.verifier.contract.functions.consentToken().call()}]
        for c in contracts:
            c.update(chain_id=self.chain_id, code_bytes=len(w3.eth.get_code(c["address"])), explorer=self.explorer("address", c["address"]))
        write_json(self.path("chain", "contracts.json"), contracts)

        def earlier(row, action, operation=None, consent_id=None):
            """The last row of the same consent before `row` that started the step it confirms."""
            for e in reversed(ledger[:ledger.index(row)]):
                if e.get("consent_id") == (consent_id or row.get("consent_id")) and e.get("action") == action and (
                        operation is None or ((e.get("metadata") or {}).get("lifecycle") or {}).get("operation") == operation):
                    return e
            return None

        entries = []
        for e in ledger:
            m = e.get("metadata") if isinstance(e.get("metadata"), dict) else {}
            if e.get("tx_hash") and e.get("action") == "ONCHAIN_MINT":
                start = earlier(e, "MINT_SBT") or earlier(e, "STATE_CHECK", "TRANSITION", m.get("predecessor_id"))
                entries.append(("mint", e["tx_hash"], e, start))
            elif e.get("tx_hash") and e.get("action") == "ONCHAIN_REVOKE":
                entries.append(("revoke", e["tx_hash"], e, earlier(e, "STATE_CHECK", "TRANSITION")))
            elif e.get("tx_hash"):
                entries.append((str(e.get("action")).lower(), e["tx_hash"], e, None))
            elif e.get("action") == "DATA_ACCESS" and (m.get("proof_reference") or {}).get("tx_hash"):
                entries.append(("verification", m["proof_reference"]["tx_hash"], e, earlier(e, "STATE_CHECK", "ACCESS")))
        receipts, events, links = [], [], []
        decoders = (("ConsentIssued", self.token.contract.events.ConsentIssued), ("ConsentRevoked", self.token.contract.events.ConsentRevoked),
                    ("ConsentVerified", self.verifier.contract.events.ConsentVerified))
        for action, tx_hash, row, start in entries:
            entry = {"scenario": scenario_of.get(row["event_id"], ""), "consent": keys.get(row.get("consent_id"), ""),
                     "consent_id": row.get("consent_id"), "action": action, "tx_hash": tx_hash,
                     "submitted_at": start["timestamp"] if start else "", "confirmed_at": row["timestamp"],
                     "latency_s": round((datetime.fromisoformat(row["timestamp"]) - datetime.fromisoformat(start["timestamp"])).total_seconds(), 3)
                     if start else "", "explorer_link": self.explorer("tx", tx_hash)}
            try:
                receipt, sent = w3.eth.get_transaction_receipt(tx_hash), w3.eth.get_transaction(tx_hash)
                block = w3.eth.get_block(receipt["blockNumber"])
                price = int(receipt.get("effectiveGasPrice") or sent.get("gasPrice") or 0)
                names = []
                for name, decoder in decoders:
                    for found in decoder().process_receipt(receipt, errors=DISCARD):
                        names.append(name)
                        events.append({"tx_hash": tx_hash, "block_number": int(receipt["blockNumber"]), "event": name,
                                       "arguments": {k: (v if isinstance(v, bool) else str(v)) for k, v in dict(found["args"]).items()}})
                entry.update(status=int(receipt["status"]), block_number=int(receipt["blockNumber"]),
                             block_time_utc=datetime.fromtimestamp(int(block["timestamp"]), timezone.utc).isoformat(),
                             gas_used=int(receipt["gasUsed"]), effective_gas_price_wei=price,
                             fee_eth=str(w3.from_wei(int(receipt["gasUsed"]) * price, "ether")), to=receipt["to"],
                             event=", ".join(names), **{"from": receipt["from"]})
            except Exception as error:
                entry.update(status="NOT FOUND", error=str(error)[:200])
            receipts.append(entry)
            links.append({"kind": "transaction", "scenario": entry["scenario"], "action": f"{action} {entry['consent']}".strip(),
                          "hash_or_address": tx_hash, "block": entry.get("block_number", ""), "link": entry["explorer_link"]})
        columns = ["scenario", "consent", "action", "tx_hash", "status", "block_number", "block_time_utc", "gas_used",
                   "effective_gas_price_wei", "fee_eth", "from", "to", "event", "submitted_at", "confirmed_at", "latency_s", "explorer_link"]
        write_json(self.path("chain", "receipts.json"), receipts)
        write_csv(self.path("chain", "receipts.csv"), columns, receipts)
        write_json(self.path("chain", "events.json"), events)
        write_json(self.path("chain", "calls.json"), self.calls)
        links = [{"kind": "contract", "scenario": "", "action": c["contract"], "hash_or_address": c["address"], "block": c.get("deploy_block") or "",
                  "link": c["explorer"]} for c in contracts] + links
        write_csv(self.path("links.csv"), ["kind", "scenario", "action", "hash_or_address", "block", "link"], links)
        lines = ["# Links of the final run", "",
                 "One line for each contract and each transaction, in the order of the run." if self.sepolia else
                 f"The chain {self.chain_id} has no public explorer: the addresses and the hashes are listed without links.", ""]
        lines += [f"- {x['kind']} | {x['scenario']} | {x['action']} | {x['link'] or x['hash_or_address']}"
                  + (f" | block {x['block']}" if x["block"] != "" else "") for x in links]
        with open(self.path("links.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return receipts

    def run_tests(self):
        """The automated test suite, in a process that knows neither the database nor the chain of the run."""
        junit = self.path("tests", "junit.xml")
        started = time.time()
        done = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"],
                              cwd=REPO, env=child_environment(os.environ), capture_output=True, text=True)
        with open(self.path("tests", "pytest.txt"), "w", encoding="utf-8") as f:
            f.write(done.stdout + ("\n[standard error]\n" + done.stderr if done.stderr.strip() else ""))
        tail = [line for line in done.stdout.splitlines() if re.search(r"\d+ (passed|failed|error)", line)]
        line = (tail[-1].strip("= ") if tail else f"no result line (exit code {done.returncode})") + f" | {int(time.time() - started)} s"
        with open(self.path("tests", "summary.txt"), "w", encoding="utf-8") as f:
            f.write(line + "\n")
        return line, test_results(junit)

    def close(self, with_tests=True):
        """The closing evidence: the auditor's review with the verification tool, the ledger, the receipts, the links,
        the test suite, the summary and the README of the folder."""
        self.say("Closing evidence")
        ledger = self.export_ledger()
        # The auditor's review and the verification cover the ledger as it stands at the closing. When rows were
        # added after the last verification (a scenario was run after it), both are made again and CS-13 is judged
        # from the new output.
        covered = self.state.get("verified_rows")
        if "CS-13:" in self.state["done"] and covered != len(ledger):
            self.state["done"].remove("CS-13:")
            self.state["results"].setdefault("CS-13", {}).pop("result", None)
            self.current = "CS-13"
            self.remark(f"the review and the verification were made again: the ledger holds {len(ledger)} rows, and the "
                        f"verification before covered {covered if covered is not None else 'an unknown number'}")
        self.run_part("close", "CS-13", "", "cs_13")
        ledger = self.export_ledger()
        # The time of every decision of the run is the block timestamp. A row that names another source (the server
        # clock) fails the run, whatever the scenario it belongs to expected: the row and its scenario are named.
        from tools.verify_poc import time_sources
        decided, other = time_sources(ledger)
        scenario_of = self.scenario_of()
        self.state["time_sources"] = {"rows": len(decided), "other": [dict(row, scenario=scenario_of.get(row["event_id"], "")) for row in other]}
        self.say("  " + time_source_words(self.state["time_sources"]))
        receipts = self.export_chain(ledger)
        os.makedirs(os.path.join(self.out, "timings"), exist_ok=True)
        with open(self.path("timings", "README.md"), "w", encoding="utf-8") as f:
            f.write("# Timings\n\nThe final run measures nothing here. The timings of the local operations are made with\n"
                    "tools/measure_local_timing.py, over at least 1,000 trials, from the repository root:\n\n"
                    f"    N_RUNS=1000 TIMING_OUT={os.path.relpath(os.path.join(self.out, 'timings', 'metrics_local.json'), REPO)} "
                    "python3 tools/measure_local_timing.py\n\n"
                    "It reports the median, the mean, the minimum and the maximum of the credential check, the identity\n"
                    "verification of Algorithm 5.1, the signature recovery, the decision rule and the request path.\n"
                    "The gas, the fee and the latency of every transaction of this run are in ../chain/receipts.csv.\n")
        line, tests = self.run_tests() if with_tests else ("the test suite was not run", {})
        self.check_build("closing")                # the files are still those of the first start, or README.md says which are not
        self.state["tests"] = line
        self.state["closed"] = True
        self.save()
        scenarios = [self.scenarios[i] for i in self.order]
        counts = write_summary(os.path.join(self.out, "summary"), scenarios, self.state["results"], tests)
        self.write_readme(counts, line, receipts)
        return counts

    def write_readme(self, counts=None, tests=None, receipts=None):
        scenarios = [self.scenarios[i] for i in self.order]
        counts = counts or count_results(summary_rows(scenarios, self.state["results"]))
        build = self.state.get("build") or build_identity()
        changes = self.state.get("build_changes", [])
        lines = ["# Evidence of the final run of the HALAH prototype", "",
                 f"Started {self.state['started']}. Chain {self.chain_id} ({'Sepolia' if self.sepolia else 'not Sepolia'}).",
                 f"Build at the first start: {build_words(build)} (the files and their checksums: run_state.json, \"build\")."]
        if changes:
            lines += ["THE BUILD CHANGED DURING THE RUN. This folder holds the work of more than one build:"]
            lines += [f"- {c['at']} ({c['when']}): commit {c['commit']}, checksum {c['checksum'][:12]}. Files that differ from the first "
                      f"start: {', '.join(c['files']) or 'none, the commit alone'}." + (" Accepted at that start." if c.get("accepted") else "")
                      for c in changes]
        else:
            lines += ["The files of the build were the same at every start" + (" and at the closing." if self.state.get("closed") else " so far.")]
        lines += [f"ConsentSBTv4 {self.token.address}, ConsentDecisionVerifier {self.verifier.address} (all four contracts: chain/contracts.json).", "",
                  "Stages:"]
        lines += [f"- stage {n}: started {s.get('started', '-')}, ended {s.get('ended', 'not ended')}" for n, s in sorted(self.state["stages"].items())]
        lines += [f"- the time of the chain was moved by {m['seconds']} seconds at {m['at']} ({m['why']})" for m in self.state["time_moves"]]
        lines += ["", f"Scenarios: {counts[PASS]} PASS, {counts[FAIL]} FAIL, {counts[ERROR]} ERROR, {counts[NOT_RUN]} NOT RUN "
                      f"of {len(scenarios)}." + ("" if self.state.get("closed") else " The run is not closed yet."),
                  f"Automated test suite: {tests or self.state.get('tests') or 'not run yet'}.",
                  time_source_words(self.state.get("time_sources")),
                  f"Transactions with a receipt: {len(receipts) if receipts is not None else 'see chain/receipts.csv'}.", "",
                  "| File | What it holds |", "|---|---|",
                  "| summary/summary.md, .csv, .json | one line for each scenario: class, expected and observed decision and deny code, result, evidence |",
                  "| screens/ | one screenshot for each step that has a screen, named by scenario |",
                  "| ledger/audit_ledger.json, .csv | every row of the audit ledger of the run, in order |",
                  "| ledger/by_scenario/ | the rows that each scenario added |",
                  "| ledger/case_study.json | the rows of Layan's consent and of its re-issue, in order |",
                  "| service/ | the answers of the service calls, which ran on copies of the records with a ledger of the tool |",
                  "| chain/contracts.json | the four contracts: address, code size, what they read back |",
                  "| chain/receipts.json, .csv | every transaction: block, gas, fee, event, latency from the ledger timestamps |",
                  "| chain/events.json | the decoded events of those receipts |",
                  "| chain/calls.json | every call that sent nothing: the attacks on the contracts and the refused proofs |",
                  "| links.md, links.csv | one explorer link for each contract and each transaction |",
                  "| verification/verify_poc.txt | the output of the independent verification tool over the database of the run |",
                  "| tests/ | the output of the automated test suite of the same build |",
                  "| timings/README.md | the commands for the timing runs, which the final run does not make |",
                  "| preflight.txt, preflight.json | the read-only checks before anything was sent |",
                  "| run_state.json | the state of the run: the build, stages, consent identifiers, what each scenario observed. It holds no key |",
                  "| app/ | the stores of the run (database, vault, key store, status list, log). Not evidence to publish |"]
        with open(self.path("README.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------------------------------------
# The preflight and the command
# ---------------------------------------------------------------------------------------------------------
def preflight(run, signer, stage):
    """The read-only checks before anything is sent. Returns the lines as printed. Stops at the first thing that is missing."""
    from blockchain import deploy_v4
    from services import identity_service, zk_decision_service
    w3 = run.w3
    lines, facts = [], {}

    def say(name, value):
        facts[name] = value
        lines.append(f"{name:<34} {value}")
    expected = int(os.environ.get("CHAIN_ID") or SEPOLIA)
    say("Versions", ", ".join(f"{name} {version}" for name, version in versions().items()))
    say("Chain", f"{run.chain_id} ({'Sepolia' if run.sepolia else 'not Sepolia'}), block {w3.eth.block_number}")
    if run.chain_id != expected:
        raise Stop(f"The endpoint answers for chain {run.chain_id} and chain {expected} is expected (CHAIN_ID).")
    addresses = {"token": os.environ["CONTRACT_V4_ADDRESS"], "verifier": os.environ["VERIFIER_ADDRESS"],
                 "poseidon": os.environ["POSEIDON_ADDRESS"], "groth16": os.environ["GROTH16_VERIFIER_ADDRESS"]}
    if not zk_decision_service.decision_available():
        raise Stop("The decision circuit is not built on this machine (zk/build, and node): no proof could be made.")
    check_machine()
    constants = deploy_v4.verification_key_constants()
    try:
        read = deploy_v4.check_deployment(w3, addresses, signer=signer, key_constants=constants)
    except deploy_v4.DeployError as error:
        raise Stop(f"The deployed contracts are not the ones this build expects: {error}.") from None
    for name, key in deploy_v4.ORDER:
        say(name, addresses[key])
    say("Owner of ConsentSBTv4", f"{read['owner']} (the configured signer)")
    say("Verification key", "zk/build matches the deployed Groth16 verifier")
    say("Tokens issued so far", read["consent_count"])
    valid = {did: identity_service.verify_identity(did, role=role).valid
             for did, role in [(f"did:parent:{x}", "guardian") for x in "ABCDE"] + [(CLINICIAN, "doctor"), (REGISTRAR, "doctor")]}
    revoked_in_the_run = "S5-11:" in run.state["done"]
    needed = [did for did, good in valid.items() if not good and did != "did:parent:E" and not (did == "did:parent:D" and revoked_in_the_run)]
    if needed:
        raise Stop(f"No valid demonstration credential for {', '.join(needed)} (Algorithm 5.1): the scenarios need them.")
    say("Credentials valid by Algorithm 5.1", ", ".join(did for did, good in valid.items() if good))
    if not valid["did:parent:E"]:
        say("did:parent:E", "no valid credential: scenario S5-03 will be reported NOT RUN")
    balance, price = w3.eth.get_balance(signer), w3.eth.gas_price
    cost = ESTIMATED_GAS * price
    say("Balance of the signer", f"{w3.from_wei(balance, 'ether'):.6f} ETH")
    say("Gas price", f"{w3.from_wei(price, 'gwei'):.4f} gwei")
    say("Estimated cost of one whole run", f"about {ESTIMATED_GAS:,} gas = {w3.from_wei(cost, 'ether'):.6f} ETH at this price")
    if stage == 1 and balance < cost:
        raise Stop(f"The balance of the signer ({w3.from_wei(balance, 'ether'):.6f} ETH) is below the estimated cost of the run "
                   f"({w3.from_wei(cost, 'ether'):.6f} ETH at {w3.from_wei(price, 'gwei'):.4f} gwei).")
    now = run.trusted()
    say("Time of the chain", f"{now['time']:%Y-%m-%d %H:%M:%S} (block {now['block_number']}, time zone of this machine)")
    say("Server clock", f"{datetime.now():%Y-%m-%d %H:%M:%S}")
    return lines, facts


def evidence_folder(args, network):
    """The folder of the run: the one that is named, else a run of this network that is not closed, else a new one."""
    named = args.out or os.environ.get("FINAL_RUN_OUT")
    if named:
        return os.path.abspath(named)
    base = os.path.join(REPO, "evidence")
    for name in sorted(os.listdir(base) if os.path.isdir(base) else [], reverse=True):
        state = os.path.join(base, name, "run_state.json")
        if name.startswith("final_run_") and name.endswith("_" + network) and os.path.exists(state):
            with open(state, encoding="utf-8") as f:
                if not json.load(f).get("closed"):
                    return os.path.join(base, name)
    return os.path.join(base, f"final_run_{datetime.now():%Y-%m-%d}_{network}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 tools/final_run.py", description="The final run of the HALAH prototype.")
    parser.add_argument("--out", help="the evidence folder (default: evidence/final_run_<date>_<network>, or FINAL_RUN_OUT)")
    parser.add_argument("--stage", choices=("1", "2", "3", "close"), help="run this stage (default: the stage that is due)")
    parser.add_argument("--only", help="run these scenarios alone, for example S6-03,S6-04")
    parser.add_argument("--same-day", action="store_true",
                        help="a trial: run stage 3 on the day of the transition (CS-08 is then recorded as failed)")
    parser.add_argument("--accept-build-change", action="store_true",
                        help="continue a run although the files of the build have changed since its first start")
    args = parser.parse_args(argv)
    os.chdir(REPO)
    about, scenarios = load_scenarios()
    only = [s.strip() for s in args.only.split(",") if s.strip()] if args.only else None
    unknown = [s for s in (only or []) if s not in {x["id"] for x in scenarios}]
    if unknown:
        raise Stop(f"No scenario of the list is called {', '.join(unknown)}.")

    import blockchain.contract                     # reads the .env file of the repository, as the application does
    missing = missing_settings(os.environ)
    if missing:
        raise Stop(" ".join(missing))
    from eth_account import Account
    try:
        signer = Account.from_key(os.environ["PRIVATE_KEY"]).address
    except Exception:
        raise Stop("PRIVATE_KEY is not a usable key.") from None
    # The application is given the settings as they are. The tool itself keeps no key: it sends nothing.
    application = dict(os.environ)
    del os.environ["PRIVATE_KEY"]

    try:
        from web3 import Web3
        chain_id = Web3(Web3.HTTPProvider(os.environ["RPC_URL"], request_kwargs={"timeout": 30})).eth.chain_id
    except Exception as error:
        raise Stop(f"The chain could not be reached at RPC_URL ({str(error).splitlines()[0][:200]}).") from None
    out = evidence_folder(args, "sepolia" if chain_id == SEPOLIA else f"chain{chain_id}")
    os.makedirs(os.path.join(out, "app"), exist_ok=True)
    with open(os.path.join(out, "app", ".gitignore"), "w", encoding="utf-8") as f:
        f.write("*\n")
    run = Run(out, about, scenarios)
    run.connect()
    run.same_contracts()
    # The stores: the application writes the database, the vault and the key store of the run. The tool keeps its own
    # services away from them, and shares one file with the application, the credential status list.
    database = os.path.join(out, "app", "halah_final.db")
    status_list = os.path.join(out, "app", "credential_status.json")
    application.update(HALAH_DB_PATH=database, HALAH_STATUS_LIST_PATH=status_list, CHAIN_ID=str(run.chain_id))
    for name in ("HALAH_VAULT_PATH", "HALAH_KEYSTORE_PATH"):
        application.pop(name, None)
    os.environ.update(HALAH_DB_PATH=":memory:", HALAH_VAULT_PATH=":memory:", HALAH_KEYSTORE_PATH=":memory:",
                      HALAH_STATUS_LIST_PATH=status_list, CHAIN_ID=str(run.chain_id))

    stage = args.stage or str(run.due_stage())
    print(f"Evidence folder: {out}")
    print(f"Stage that is due: {run.due_stage()}" + ("" if args.stage is None else f" (asked for: {args.stage})"))
    lines, facts = preflight(run, signer, int(stage) if stage.isdigit() else 0)
    print("\n".join(lines))
    with open(os.path.join(out, "preflight.txt"), "a", encoding="utf-8") as f:
        f.write(f"--- {datetime.now().isoformat(timespec='seconds')} stage {stage}\n" + "\n".join(lines) + "\n")
    write_json(os.path.join(out, "preflight.json"), facts)
    first_start = "build" not in run.state
    differ = run.check_build(f"start of stage {stage}", accept=args.accept_build_change)
    print(f"Build of this run: {build_words(run.state['build'])}. " + (
        "Do not pull and do not edit the repository until the run is closed: the application reads its files again at "
        "every new session, and the tool compares them at every start and at the closing." if first_start else
        f"The files differ from the first start ({len(differ)}): README.md of the folder names them." if differ else
        "The files are the same as at the first start."))
    closing = False
    try:
        url = run.start_application(application)
        run.start_browser(url)
        print(f"The application of the run answers at {url} (database {database})")
        run.check_screens()
        if stage == "close":
            counts, closing = run.close(), True
        else:
            run.run_stage(int(stage), only, args.same_day)
            # on a chain whose time can be moved, the stages that follow run in the same go
            while not only and not run.sepolia and args.stage is None and run.due_stage() in (2, 3) and run.due_stage() != int(stage):
                stage = str(run.due_stage())
                run.run_stage(int(stage), None, args.same_day)
            if not only and args.stage is None and run.due_stage() == "close":
                counts, closing = run.close(), True
            else:
                counts = write_summary(os.path.join(out, "summary"), scenarios, run.state["results"])
                run.write_readme(counts)
    finally:
        run.stop()
    return end_of_run(run, counts, len(scenarios), closing)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Stop as stop:
        sys.exit(f"STOPPED: {stop}")
