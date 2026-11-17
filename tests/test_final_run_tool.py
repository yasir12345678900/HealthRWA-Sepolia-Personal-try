"""The final-run tool (tools/final_run.py), as far as it runs without a chain and without a browser: the scenario list
and its order, the comparison of observed with expected, the summary table, the messages when a setting is missing, the
environment of the child processes, the stores it may only read, and the request path on a copy with a ledger of the
tool. The run itself needs the application, a chain and a browser, and is made outside the test suite."""
import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from types import SimpleNamespace
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NINE = ("OUT-OF-SCOPE", "PURPOSE-MISMATCH", "CONTEXT-MISMATCH", "PRE-VALIDITY", "POST-VALIDITY", "AWAITING-TRIGGER",
        "TRANSITION-PENDING", "EXPIRED", "REVOKED")
CLINICIAN = "did:hospital:001"
G = ["did:parent:A", "did:parent:B"]


@pytest.fixture()
def tool():
    from tools import final_run
    return final_run


@pytest.fixture()
def listed(tool):
    about, scenarios = tool.load_scenarios()
    return SimpleNamespace(about=about, scenarios=scenarios, by_id={s["id"]: s for s in scenarios})


def _run(tool, listed, folder):
    return tool.Run(str(folder), listed.about, listed.scenarios, say=lambda line: None)


# ---- the scenario list and the order of the run ---------------------------------------------------------------------------

def test_scenario_list_is_complete_and_every_deny_code_is_one_of_the_nine(tool, listed):
    ids = [s["id"] for s in listed.scenarios]
    assert len(ids) == 58 and len(set(ids)) == 58
    counts = {c: sum(1 for s in listed.scenarios if s["class"] == c) for c in ("valid", "negative", "adversarial", "case study")}
    assert counts == {"valid": 9, "negative": 17, "adversarial": 19, "case study": 13}
    for s in listed.scenarios:
        assert s["deny_code"] is None or s["deny_code"] in NINE
        assert s["expected_check"].get("outcome") and s["steps"] and s["evidence"] and s["runs_in"]
    reached = {s["deny_code"] for s in listed.scenarios if s["deny_code"]}
    assert reached == set(NINE) == set(tool.NINE)                     # every code of the thesis is reached by a scenario
    assert tool.load_scenarios()[0]["deny_codes"] == list(NINE)
    with pytest.raises(tool.Stop):
        tool.load_scenarios(os.path.join(ROOT, "tools", "no_such_list.json"))


def test_every_scenario_has_its_place_in_the_run_and_every_step_a_function(tool, listed):
    stages = tool.Run.STAGES
    planned = [sid for steps in stages.values() for sid, _, _ in steps]
    assert set(planned) == set(listed.by_id)                          # no scenario of the list is left out of the run
    for stage, steps in stages.items():
        for sid, part, function in steps:
            assert callable(getattr(tool.Run, function)), function
            listed_stage = listed.by_id[sid]["stage"]
            # a scenario runs in its own stage. Three of them begin in stage 1, and the auditor's review closes the run
            assert stage == listed_stage or (stage == 1 and sid in ("S6-11", "S6-08", "S6-09")) or (stage == "close" and sid == "CS-13")
    parts = [(sid, part) for steps in stages.values() for sid, part, _ in steps]
    assert len(parts) == len(set(parts))
    # the guardian's revocation of S6-02 stands between the two parts of S7-10, and K22 is revoked late
    first = [sid for sid, _, _ in stages[1]]
    assert first.index("S7-10") < first.index("S6-02", first.index("S7-10")) < len(first) - 1 - first[::-1].index("S7-10")
    assert first.index("S6-20") > max(first.index(s) for s in ("S6-01", "S7-01", "S6-03", "S6-06", "S7-04", "S7-07", "S7-09", "S5-09", "S5-10"))
    assert first.index("S6-19") > first.index("S6-20") and first.index("S5-11") > first.index("S5-03")


def test_every_screenshot_of_the_list_is_taken_by_the_tool(listed):
    with open(os.path.join(ROOT, "tools", "final_run.py"), encoding="utf-8") as f:
        source = f.read()
    named = [e[8:-4] for s in listed.scenarios for e in s["evidence"] if e.startswith("screens/")]
    assert len(named) > 80 and len(named) == len(set(named))
    missing = [name for name in named if f'"{name}"' not in source]
    assert missing == []


# ---- observed against expected ---------------------------------------------------------------------------------------------

def test_scenario_passes_only_when_decision_deny_code_and_failed_checks_are_the_expected_ones(tool, listed):
    s = listed.by_id["S6-03"]                                         # over-scope: DENIED, VP, ACTIVE, OUT-OF-SCOPE
    good = {"outcome": "DENIED", "failed_checks": ["VP"], "state": "ACTIVE", "deny_code": "OUT-OF-SCOPE"}
    assert tool.compare(s, good) == ("PASS", [])
    result, why = tool.compare(s, dict(good, deny_code="PURPOSE-MISMATCH"))
    assert result == "FAIL" and why == ["deny code: observed 'PURPOSE-MISMATCH', expected 'OUT-OF-SCOPE'"]
    assert tool.compare(s, dict(good, outcome="GRANTED"))[0] == "FAIL"
    assert tool.compare(s, dict(good, failed_checks=["VP", "VL"]))[0] == "FAIL"
    assert tool.compare(s, {})[0] == "FAIL"                           # nothing observed is not a pass
    # a scenario without a deny code fails when a code was recorded
    a = listed.by_id["S5-04"]
    seen = {"outcome": "DENIED", "failed_checks": ["VA", "VL"], "state": "PENDING_SIGNATURE", "deny_code": None}
    assert tool.compare(a, seen)[0] == "PASS" and tool.compare(a, dict(seen, deny_code="REVOKED"))[0] == "FAIL"
    # "failed_checks_include" asks for these checks among the failed ones
    r = listed.by_id["S5-06"]
    seen = {"outcome": "REFUSED", "signature_verifies": False, "failed_checks": ["VI", "VA", "VL"]}
    assert tool.compare(r, seen)[0] == "PASS" and tool.compare(r, dict(seen, failed_checks=["VA", "VL"]))[0] == "FAIL"
    # a further check of the scenario that is false fails it, and is named
    result, why = tool.compare(s, dict(good, checks={"nothing is released": True, "the row has the scope": False}))
    assert result == "FAIL" and why == ["check failed: the row has the scope"]
    # the request of CS-08 made on the day of the transition (a trial with --same-day) is a failed scenario
    d = listed.by_id["CS-08"]
    seen = {"outcome": "GRANTED", "failed_checks": [], "modules_released": ["Observation", "Medication"], "deny_code": None}
    assert tool.compare(d, dict(seen, following_day=True)) == ("PASS", [])
    assert tool.compare(d, dict(seen, following_day=False)) == ("FAIL", ["following_day: observed False, expected True"])


def test_failed_scenario_does_not_hide_the_others_in_the_run_or_in_the_summary(tool, listed, tmp_path):
    run = _run(tool, listed, tmp_path)
    run.ledger = lambda: []                                           # no application behind this run
    run.screens = SimpleNamespace(p=SimpleNamespace(screenshot=lambda **kw: None))
    done = []

    def good():
        done.append(run.current)
        run.note(outcome="DENIED", failed_checks=["VP"], state="ACTIVE", deny_code={"S6-03": "OUT-OF-SCOPE", "S6-05": "PURPOSE-MISMATCH"}[run.current])

    def broken():
        raise RuntimeError("the page did not answer")

    def missing():
        raise tool.NotRun("the consent K22 was not created in this run")
    run.s6_03, run.s6_04, run.s6_05, run.s6_06 = good, broken, good, missing
    for sid in ("S6-03", "S6-04", "S6-05", "S6-06"):
        run.run_part(1, sid, "", "s" + sid[1:].lower().replace("-", "_"))
    assert done == ["S6-03", "S6-05"]                                 # the scenario after the failed one ran
    results = run.state["results"]
    assert [results[s]["result"] for s in ("S6-03", "S6-04", "S6-05", "S6-06")] == ["PASS", "ERROR", "PASS", "NOT RUN"]
    assert results["S6-04"]["message"] == "RuntimeError: the page did not answer"
    assert results["S6-06"]["message"] == "the consent K22 was not created in this run"
    assert "the page did not answer" in open(tmp_path / "errors.log").read()
    # the summary holds every scenario of the list: the four that ran, and the others as NOT RUN
    with open(tmp_path / "summary" / "summary.json") as f:
        summary = json.load(f)
    assert summary["counts"] == {"PASS": 2, "FAIL": 0, "ERROR": 1, "NOT RUN": 55} and len(summary["rows"]) == 58
    row = {r["scenario"]: r for r in summary["rows"]}
    assert (row["S6-03"]["expected deny code"], row["S6-03"]["observed deny code"], row["S6-03"]["result"]) == ("OUT-OF-SCOPE", "OUT-OF-SCOPE", "PASS")
    assert row["S6-04"]["result"] == "ERROR" and "the page did not answer" in row["S6-04"]["remark"]
    assert row["S7-01"]["result"] == "NOT RUN" and row["S7-01"]["remark"] == "not reached in this run"
    text = open(tmp_path / "summary" / "summary.md").read()
    assert "58 scenarios: 2 PASS, 0 FAIL, 1 ERROR, 55 NOT RUN." in text and "| S6-05 | negative |" in text
    assert open(tmp_path / "summary" / "summary.csv").read().count("\n") == 59
    # a second start continues: what passed is not run again, and the failed scenario is tried again
    again = _run(tool, listed, tmp_path)
    again.ledger = lambda: []
    again.s6_03 = broken
    again.s6_04 = lambda: again.note(outcome="DENIED", failed_checks=["VP"], state="ACTIVE", deny_code="OUT-OF-SCOPE")
    again.run_part(1, "S6-03", "", "s6_03")
    again.run_part(1, "S6-04", "", "s6_04")
    assert again.state["results"]["S6-03"]["result"] == "PASS" and again.state["results"]["S6-04"]["result"] == "PASS"


def test_failed_mint_is_submitted_once_more_and_a_second_failure_is_an_error(tool, listed, tmp_path):
    run = _run(tool, listed, tmp_path)
    run.current = "S5-01"
    run.state["consents"]["K22"] = "c-1"
    clicked, ledger = [], []
    row = lambda result, **more: dict({"action": "ONCHAIN_MINT", "result": result, "consent_id": "c-1", "tx_hash": None,
                                       "block_number": None, "metadata": {"error": "the node did not answer"}}, **more)

    def anchor_again(consent_id):                                     # the click starts the anchoring job again
        clicked.append(consent_id)
        ledger.append(row("SUCCESS", tx_hash="0x" + "cd" * 32, block_number=7, metadata={"token_id": 3}))
    run.screens = SimpleNamespace(anchor_again=anchor_again)
    run.rows = lambda consent_id, action=None, result=None: [e for e in ledger if result is None or e["result"] == result]
    ledger.append(row("FAILED"))
    done = run.anchored("K22")
    assert clicked == ["c-1"] and done["result"] == "SUCCESS" and run.token_of("K22") == 3
    assert run.state["results"]["S5-01"]["transactions"] == ["0x" + "cd" * 32] and run.state["results"]["S5-01"]["blocks"] == [7]
    # a mint that fails again after the second submission is an error of the scenario, with the reason of the ledger
    ledger[:] = [row("FAILED")]
    run.screens = SimpleNamespace(anchor_again=lambda consent_id: ledger.append(row("FAILED")))
    with pytest.raises(RuntimeError) as failure:
        run.anchored("K22")
    assert str(failure.value) == "the mint of K22 failed twice: the node did not answer"
    # the row of a re-issue holds the token as "SBT-<n>": both forms are read
    ledger[:] = [row("SUCCESS", metadata={"token_id": "SBT-14"})]
    assert run.token_of("K22") == 14


def test_summary_shows_a_deny_code_only_when_it_is_one_of_the_nine(tool, listed):
    results = {"S5-04": {"result": "FAIL", "observed": {"outcome": "DENIED", "deny_code": "APPROVAL-PENDING", "failed_checks": ["VA", "VL"]},
                         "differences": ["deny code: observed 'APPROVAL-PENDING', expected None"], "consents": ["6c2f5410-b128"],
                         "transactions": ["0x" + "ab" * 32], "blocks": [12], "evidence": ["screens/S5-04_04_clinician_denied.png"]}}
    row = [r for r in tool.summary_rows(listed.scenarios, results) if r["scenario"] == "S5-04"][0]
    assert row["observed deny code"] == "" and row["observed failed checks"] == "VA, VL" and row["result"] == "FAIL"
    assert row["consent"] == "6c2f5410" and row["transactions"] == "0xababababab..." and row["blocks"] == "12"
    assert set(row) == set(tool.SUMMARY_COLUMNS)


def test_results_of_the_automated_tests_are_taken_from_the_junit_file(tool, listed, tmp_path):
    junit = tmp_path / "junit.xml"
    junit.write_text('<testsuites><testsuite>'
                     '<testcase classname="tests.test_adversarial" name="test_A1_signer_outside_G_is_not_counted"/>'
                     '<testcase classname="tests.test_identity_v2" name="test_A1_v2_signer_outside_G_is_not_counted"><failure/></testcase>'
                     '<testcase classname="tests.test_zk" name="test_real_groth16_proof_verifies"><skipped/></testcase>'
                     '<testcase classname="tests.test_core_v2" name="test_a"/><testcase classname="tests.test_core_v2" name="test_b"/>'
                     '</testsuite></testsuites>')
    results = tool.test_results(str(junit))
    assert results["tests/test_adversarial.py::test_A1_signer_outside_G_is_not_counted"] == "passed"
    assert results["tests/test_identity_v2.py::test_A1_v2_signer_outside_G_is_not_counted"] == "failed"
    assert results["tests/test_zk.py::test_real_groth16_proof_verifies"] == "skipped"
    assert tool.tests_of(listed.by_id["S5-05"], results) == ["test_A1_signer_outside_G_is_not_counted: passed",
                                                             "test_A1_v2_signer_outside_G_is_not_counted: failed"]
    assert tool.tests_of(listed.by_id["S6-03"], results) == ["tests/test_core_v2.py: 2 passed, 0 failed"]
    assert tool.test_results(str(tmp_path / "none.xml")) == {}
    assert tool.tests_of(listed.by_id["S5-05"], {})[0].endswith("not in this run")


# ---- the configuration ---------------------------------------------------------------------------------------------------

def test_each_missing_setting_stops_the_tool_with_a_plain_sentence(tool, monkeypatch, tmp_path):
    full = {"RPC_URL": "http://127.0.0.1:1", "CONTRACT_V4_ADDRESS": "0x" + "11" * 20, "VERIFIER_ADDRESS": "0x" + "22" * 20,
            "POSEIDON_ADDRESS": "0x" + "33" * 20, "GROTH16_VERIFIER_ADDRESS": "0x" + "44" * 20, "PRIVATE_KEY": "0x" + "55" * 32}
    assert tool.missing_settings(full) == []
    for name in full:
        (sentence,) = tool.missing_settings({k: v for k, v in full.items() if k != name})
        assert sentence.startswith(f"{name} is not set: ") and sentence.endswith(".")
    assert len(tool.missing_settings({"RPC_URL": "  "})) == 6         # an empty value is a missing value
    # the command stops before it starts anything, and names what is missing
    monkeypatch.setenv("FINAL_RUN_OUT", str(tmp_path / "run"))
    with pytest.raises(tool.Stop) as stopped:
        tool.main([])
    assert "CONTRACT_V4_ADDRESS is not set" in str(stopped.value) and "PRIVATE_KEY is not set" in str(stopped.value)
    assert not (tmp_path / "run").exists()
    with pytest.raises(tool.Stop) as stopped:
        tool.main(["--only", "S9-99"])
    assert str(stopped.value) == "No scenario of the list is called S9-99."
    # a key that is not a key, and a chain that does not answer
    for name, value in full.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("PRIVATE_KEY", "not a key")
    with pytest.raises(tool.Stop) as stopped:
        tool.main([])
    assert str(stopped.value) == "PRIVATE_KEY is not a usable key."
    monkeypatch.setenv("PRIVATE_KEY", full["PRIVATE_KEY"])
    with pytest.raises(tool.Stop) as stopped:
        tool.main([])
    assert str(stopped.value).startswith("The chain could not be reached at RPC_URL")
    assert full["PRIVATE_KEY"] not in str(stopped.value) and not (tmp_path / "run").exists()
    assert os.environ.get("PRIVATE_KEY") is None                      # the tool itself keeps no key


def test_child_process_of_the_test_suite_knows_neither_the_database_nor_the_chain_of_the_run(tool):
    env = {"PATH": "/usr/bin", "HOME": "/root", "HALAH_DB_PATH": "/run/app/halah_final.db", "PRIVATE_KEY": "0xkey",
           "RPC_URL": "https://node", "CONTRACT_ADDRESS": "0x1", "CONTRACT_V4_ADDRESS": "0x2", "VERIFIER_ADDRESS": "0x3",
           "POSEIDON_ADDRESS": "0x4", "GROTH16_VERIFIER_ADDRESS": "0x5", "CONTRACT_V4_DEPLOY_BLOCK": "9", "CHAIN_ID": "11155111",
           "HALAH_STATUS_LIST_PATH": "/run/app/credential_status.json", "HALAH_VAULT_PATH": ":memory:", "HALAH_KEYSTORE_PATH": ":memory:",
           "FINAL_RUN_OUT": "/run"}
    assert tool.child_environment(env) == {"PATH": "/usr/bin", "HOME": "/root"}
    assert env["PRIVATE_KEY"] == "0xkey"                              # the environment given is not changed


def test_evidence_folder_is_the_named_one_or_an_open_run_of_the_same_network(tool, monkeypatch, tmp_path):
    monkeypatch.setattr(tool, "REPO", str(tmp_path))
    monkeypatch.delenv("FINAL_RUN_OUT", raising=False)
    args = SimpleNamespace(out=None)
    today = datetime.now().strftime("%Y-%m-%d")
    assert tool.evidence_folder(args, "sepolia") == str(tmp_path / "evidence" / f"final_run_{today}_sepolia")
    for name, closed in (("final_run_2026-11-18_sepolia", True), ("final_run_2026-11-19_sepolia", False), ("final_run_2026-11-20_chain5", False)):
        (tmp_path / "evidence" / name).mkdir(parents=True)
        (tmp_path / "evidence" / name / "run_state.json").write_text(json.dumps({"closed": closed}))
    # a run of this network that is not closed is continued, also on a later day
    assert tool.evidence_folder(args, "sepolia") == str(tmp_path / "evidence" / "final_run_2026-11-19_sepolia")
    assert tool.evidence_folder(args, "chain5") == str(tmp_path / "evidence" / "final_run_2026-11-20_chain5")
    assert tool.evidence_folder(args, "chain7") == str(tmp_path / "evidence" / f"final_run_{today}_chain7")
    monkeypatch.setenv("FINAL_RUN_OUT", str(tmp_path / "elsewhere"))
    assert tool.evidence_folder(args, "sepolia") == str(tmp_path / "elsewhere")
    assert tool.evidence_folder(SimpleNamespace(out=str(tmp_path / "named")), "sepolia") == str(tmp_path / "named")


def test_run_is_continued_only_on_the_contracts_it_was_started_on(tool, listed, tmp_path):
    run = _run(tool, listed, tmp_path)
    run.token, run.verifier = SimpleNamespace(address="0x" + "11" * 20), SimpleNamespace(address="0x" + "22" * 20)
    run.same_contracts()                                              # the first start notes the contracts of the run
    run.save()
    again = _run(tool, listed, tmp_path)
    again.token, again.verifier = run.token, run.verifier
    again.same_contracts()                                            # the same contracts: the run is continued
    again.token = SimpleNamespace(address="0x" + "33" * 20)           # a new deployment of the token contract
    with pytest.raises(tool.Stop) as stopped:
        again.same_contracts()
    assert "started on other contracts" in str(stopped.value) and "--out" in str(stopped.value)
    assert "0x" + "11" * 20 in str(stopped.value) and "0x" + "33" * 20 in str(stopped.value)


# ---- the times the form is given ------------------------------------------------------------------------------------------

def test_windows_and_dates_of_birth_follow_the_time_of_the_chain(tool, listed):
    now = datetime(2026, 11, 17, 21, 15, 0)
    start, expiry = tool.window("now to now + 30 days", now)
    assert start == now - timedelta(seconds=60) and expiry == start + timedelta(days=30)   # started a minute before the block time
    start, expiry = tool.window("now to now + 290 seconds", now)
    assert (expiry - start).total_seconds() == 290 and start < now < expiry
    start, expiry = tool.window("now + 2 days to now + 30 days", now)
    assert start == now + timedelta(days=2) and expiry == now + timedelta(days=30)
    assert {c.get("window") for c in listed.about["consents"].values()} == {
        "now to now + 30 days", "now to now + 290 seconds", "now + 2 days to now + 30 days"}
    assert tool.eighteen_tomorrow(now) == date(2008, 11, 18)          # eighteen on the day after
    assert tool.eighteen_tomorrow(datetime(2028, 2, 28, 12, 0)) == date(2010, 3, 1)      # 29 February in a year that has none
    assert tool.next_midnight(now) == datetime(2026, 11, 18, 0, 0, 0)


def test_stage_two_and_three_wait_for_their_day_on_sepolia_and_say_when(tool, listed, tmp_path):
    run = _run(tool, listed, tmp_path)
    run.sepolia = True
    run.state["consents"] = {"KTR": "c-1", "L": "c-2"}
    run.record = lambda cid: {"transitions": [{"kind": "majority", "due": "2026-11-18T00:00:00", "done": False}]}
    run.trusted = lambda: {"time": datetime(2026, 11, 17, 23, 0, 0)}
    with pytest.raises(tool.Stop) as stopped:
        run.prepare_stage(2)
    assert str(stopped.value).startswith("Stage 2 is due after 2026-11-18 00:00")
    with pytest.raises(tool.Stop) as stopped:                         # stage 1 does not start an hour before midnight
        run.prepare_stage(1)
    assert str(stopped.value).startswith("Less than 90 minutes remain before midnight")
    run.trusted = lambda: {"time": datetime(2026, 11, 18, 0, 30, 0)}
    run.prepare_stage(2)                                              # after midnight the stage is due
    run.state["kept"]["transition_day"] = "2026-11-18"
    with pytest.raises(tool.Stop) as stopped:
        run.prepare_stage(3)
    assert "Stage 3 is due after 2026-11-19 00:00" in str(stopped.value) and "--same-day" in str(stopped.value)
    run.prepare_stage(3, same_day=True)
    run.trusted = lambda: {"time": datetime(2026, 11, 19, 0, 10, 0)}
    run.prepare_stage(3)
    assert run.state["time_moves"] == []                              # on Sepolia the time is never moved
    assert run.due_stage() == 1
    run.state["stages"] = {"1": {"ended": "x"}, "2": {"ended": "x"}}
    assert run.due_stage() == 3


# ---- the stores of the run are read, never written --------------------------------------------------------------------------

def test_tool_reads_the_vault_and_the_key_store_of_the_run_and_cannot_write_them(tool, listed, tmp_path):
    from services import data_vault, key_store
    from services.consent_service import create_consent
    app = tmp_path / "app"
    keys = key_store.KeyStore(str(app / "keystore" / "halah_keys.db"))
    vault = data_vault.DataVault(keys, str(app / "vault" / "halah_vault.db"))
    c = create_consent("did:patient:x", CLINICIAN, G, ["Observation", "Medication"], "Treatment",
                       (datetime.now() - timedelta(days=1)).isoformat(), (datetime.now() + timedelta(days=30)).isoformat())
    vault.seal(c, {"Observation": [{"value": 1}], "Medication": [{"value": 2}]})
    run = _run(tool, listed, tmp_path)
    kept = run.sealed_copy(c.consent_id)                              # the ciphertext as the file holds it, and no key
    assert sorted(kept) == ["Medication", "Observation"] and set(kept["Observation"]) >= {"ciphertext", "nonce", "key_id"}
    assert "key" not in kept["Observation"] and run.key_references(c.consent_id) == keys.key_ids(c.consent_id)
    assert run.destruction_record(c.consent_id) is None
    reader = run.read_only_vault()
    assert reader.modules(c.consent_id) == ["Medication", "Observation"] and reader.key_store.has_key(c.consent_id)
    with pytest.raises(sqlite3.OperationalError):                     # the connection is read-only: nothing can be deleted
        reader.delete(c.consent_id)
    with pytest.raises(sqlite3.OperationalError):
        reader.key_store.destroy(c.consent_id)
    assert vault.has_copy(c.consent_id) and keys.has_key(c.consent_id)
    # after the application has shredded the consent, the reader sees it and no kept blob opens
    vault.delete(c.consent_id)
    keys.destroy(c.consent_id)
    assert run.sealed_copy(c.consent_id) == {} and run.key_references(c.consent_id) == {}
    assert sorted(run.destruction_record(c.consent_id)["modules"]) == ["Medication", "Observation"]
    reader = run.read_only_vault()
    with pytest.raises(key_store.KeyDestroyedError):
        reader.key_store.decrypt(c.consent_id, "Observation", bytes.fromhex(kept["Observation"]["nonce"]), bytes.fromhex(kept["Observation"]["ciphertext"]))
    # a run without stores yet is read as an empty one
    assert _run(tool, listed, tmp_path / "new").read_only_vault().modules(c.consent_id) == []
    assert _run(tool, listed, tmp_path / "new").sealed_copy(c.consent_id) == {}


def test_request_path_on_a_copy_writes_to_the_ledger_of_the_tool_and_to_no_store(tool):
    from database import audit_db, consent_db
    from services import commitment_service, data_vault, identity_service as ids, request_service, trigger_service
    from services.consent_service import create_consent
    c = create_consent("did:patient:x", CLINICIAN, G, ["Observation"], "Treatment", (datetime.now() - timedelta(days=1)).isoformat(),
                       (datetime.now() + timedelta(days=30)).isoformat(), threshold=2, context="AU")
    commitment_service.commit_consent(c)
    for g in G:
        signature, address = ids.sign_consent_v2(g, c.consent_id, c.commitment)
        c.signatures.append(g)
        c.signature_data[g] = {"scheme": "EIP-712", "version": 2, "signer": address, "signature": signature}
    c.token_id = f"SBT-LOCAL-{c.consent_id[:8]}"
    ledger = tool.ToolLedger()
    trigger_service.add_trigger(c, "Hospital admission confirmed", attester_role="doctor", actor_did=c.patient_did,
                                actor_role="Patient", audit=ledger.log, save=tool.keep_nothing)
    before = len(audit_db.get())
    out = request_service.submit_request(c, CLINICIAN, ["Observation"], "Treatment", "AU", audit=ledger, save=tool.keep_nothing)
    assert out["outcome"] == "DENIED" and out["deny_code"] == "AWAITING-TRIGGER" and out["failed_checks"] == ["VL"]
    # the rows of the request, the move into SUSPENDED included, are in the ledger of the tool
    assert [e["action"] for e in ledger.get()] == ["ADD_TRIGGER", "IDENTITY_VERIFICATION", "CONDITION_CHECK", "STATE_CHECK", "DATA_ACCESS"]
    assert all(e["ledger"] == "of the tool" for e in ledger.get())
    # and nothing reached the ledger, the consent store or the vault of the application
    assert len(audit_db.get()) == before and consent_db.get(c.consent_id) is None
    assert not data_vault.default_vault().has_copy(c.consent_id)


# ---- the application of the run, the parametrized tests in the summary ------------------------------------------------------

def test_application_of_the_run_is_started_without_the_file_watcher(tool, listed, tmp_path, monkeypatch):
    command = tool.application_command(18999)
    assert command[command.index("--server.fileWatcherType") + 1] == "none"
    assert command[command.index("--server.port") + 1] == "18999" and command[1:5] == ["-m", "streamlit", "run", "app.py"]
    started = []

    def process(args, **options):                                     # stands for the process of the application
        started.append(list(args))
        return SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(tool.subprocess, "Popen", process)
    monkeypatch.setattr(tool.urllib.request, "urlopen", lambda url, timeout=3: SimpleNamespace(status=200))
    url = _run(tool, listed, tmp_path).start_application({})
    (used,) = started                                                 # the run starts the application with that command
    assert used[used.index("--server.fileWatcherType") + 1] == "none" and url.endswith(used[used.index("--server.port") + 1])


def test_parametrized_test_is_counted_by_its_cases_in_the_summary(tool, listed, tmp_path):
    name = "test_circuit_gives_no_proof_for_a_request_outside_the_consent"
    junit = tmp_path / "junit.xml"
    junit.write_text('<testsuites><testsuite>'
                     + "".join(f'<testcase classname="tests.test_zk_decision" name="{name}[{case}]"/>' for case in ("expired", "revoked", "role"))
                     + '<testcase classname="tests.test_zk_decision" name="test_request_outside_the_consent_is_refused_before_the_prover[expired]">'
                       '<failure/></testcase>'
                       '<testcase classname="tests.test_zk_decision" name="test_request_outside_the_consent_is_refused_before_the_prover[role]"/>'
                       '<testcase classname="tests.test_zk_decision" name="test_unknown_policy_terms_and_modules_are_refused"/>'
                       '</testsuite></testsuites>')
    results = tool.test_results(str(junit))
    assert tool.tests_of(listed.by_id["S7-02"], results) == [
        f"{name}: 3 passed, 0 failed", "test_request_outside_the_consent_is_refused_before_the_prover: 1 passed, 1 failed"]
    assert tool.tests_of(listed.by_id["S7-04"], results) == [f"{name}: 3 passed, 0 failed",
                                                             "test_unknown_policy_terms_and_modules_are_refused: passed"]
    # a test that has no case in the run is still named as missing, and a name that only begins alike is not counted
    assert tool.tests_of(listed.by_id["S7-02"], {f"tests/test_zk_decision.py::{name}_again[x]": "passed"})[0] == f"{name}: not in this run"
    row = [r for r in tool.summary_rows(listed.scenarios, {}, results) if r["scenario"] == "S7-02"][0]
    assert "not in this run" not in row["automated tests"]


# ---- a run that is continued ---------------------------------------------------------------------------------------------

class _Screens:
    """Stands for the screens of the application: each action adds the rows the application would add to the ledger
    `rows`, and a screenshot is an empty file. `fail` names the action after which the page does not come to rest."""

    def __init__(self, rows, folder, waiting=None, fail=None, error=TimeoutError):
        self.rows, self.folder, self.fail, self.error = rows, folder, fail, error
        self.waiting = {} if waiting is None else waiting             # consent -> its trigger still waits
        self.clicks = []
        self.p = SimpleNamespace(screenshot=lambda **kw: None)
        os.makedirs(folder, exist_ok=True)

    def row(self, consent_id, action, result, actor="did:hospital:001", scope=None, purpose=None, **metadata):
        self.rows.append({"event_id": f"e{len(self.rows) + 1}", "consent_id": consent_id, "action": action, "result": result,
                          "actor_did": actor, "scope": scope, "purpose": purpose, "metadata": metadata, "tx_hash": metadata.get("tx"),
                          "block_number": metadata.get("block")})

    def shot(self, name):
        if name:
            open(os.path.join(self.folder, f"{name}.png"), "w").close()

    def done(self, action):
        self.clicks.append(action)
        if self.fail == action:
            raise self.error("the page did not come to rest")

    def create(self, spec, shot_form=None, shot_done=None):
        consent_id = f"consent-{len(self.waiting) + 1}"
        self.waiting[consent_id] = bool(spec.get("trigger"))
        self.shot(shot_done)
        self.done("create")
        return consent_id

    def approve(self, consent_id, guardian, shot=None):
        self.row(consent_id, "SIGN_CONSENT", "SUCCESS", actor=guardian)
        if len([e for e in self.rows if e["consent_id"] == consent_id and e["action"] == "SIGN_CONSENT"]) == 2:
            self.row(consent_id, "ONCHAIN_MINT", "SUCCESS", actor="Blockchain", token_id=7, tx="0x" + "aa" * 32, block=9)
        self.done("approve")

    def request(self, consent_id, requester, scope, purpose, context, shot_before=None, shot_after=None):
        waits = self.waiting.get(consent_id, False)
        state = "SUSPENDED" if waits else "ACTIVE"
        self.row(consent_id, "CONDITION_CHECK", state, actor="System")
        self.row(consent_id, "STATE_CHECK", state, actor="System", lifecycle={"operation": "ACCESS"})
        if waits:
            self.row(consent_id, "DATA_ACCESS", "DENIED", actor=requester, scope=scope, purpose=purpose, context=context,
                     deny_code="AWAITING-TRIGGER", failed_checks=["VL"], modules_released=[], time_source="block-timestamp")
        else:
            self.row(consent_id, "DATA_ACCESS", "GRANTED", actor=requester, scope=scope, purpose=purpose, context=context,
                     deny_code=None, failed_checks=[], modules_released=list(scope), time_source="block-timestamp",
                     zk_proof_verified=True, proof_reference={"tx_hash": "0x" + "bb" * 32, "block_number": 11})
        self.shot(shot_after)
        self.done("request")

    def attest(self, consent_id, clinician, shot=None):
        if not self.waiting.get(consent_id):
            raise TimeoutError("no button 'Attest this event' on the page")     # the trigger is satisfied: the button is gone
        self.row(consent_id, "PRESENT_ATTESTATION", "SUCCESS", actor=clinician)
        self.waiting[consent_id] = False
        self.done("attest")
        self.shot(shot)


def _continued(tool, listed, folder, rows, **screens):
    """A start of the tool on the folder of a run, with the ledger `rows` and stand-in screens."""
    run = _run(tool, listed, folder)
    run.ledger = lambda: list(rows)
    run.trusted = lambda: {"time": datetime(2026, 11, 17, 10, 0, 0), "unix": 1794909600, "source": "block-timestamp"}
    run.screens = _Screens(rows, str(folder / "screens"), **screens)
    return run


def test_trigger_scenario_that_broke_off_after_the_attestation_is_completed_at_the_next_start(tool, listed, tmp_path):
    rows, waiting = [], {}
    first = _continued(tool, listed, tmp_path, rows, waiting=waiting, fail="attest")
    first.run_part(1, "S6-10", "", "s6_10")
    result = first.state["results"]["S6-10"]
    assert result["result"] == "ERROR" and result["message"] == "TimeoutError: the page did not come to rest"
    assert [(e["action"], e["result"]) for e in rows][-2:] == [("DATA_ACCESS", "DENIED"), ("PRESENT_ATTESTATION", "SUCCESS")]
    consent_id = first.state["consents"]["KTRG"]
    # the next start: nothing is edited by hand. The refused request and the attestation are read from the ledger
    again = _continued(tool, listed, tmp_path, rows, waiting=waiting)
    again.run_part(1, "S6-10", "", "s6_10")
    assert again.screens.clicks == ["request"]                        # one click: the request after the attestation
    result = again.state["results"]["S6-10"]
    assert result["result"] == "PASS" and result["differences"] == [] and again.state["consents"]["KTRG"] == consent_id
    assert result["observed"]["outcome"] == "DENIED then GRANTED" and result["observed"]["deny_code"] == "AWAITING-TRIGGER"
    assert result["observed"]["state"] == "SUSPENDED" and result["observed"]["second_outcome"] == "GRANTED"
    assert [e["result"] for e in rows if e["action"] == "DATA_ACCESS"] == ["DENIED", "GRANTED"]
    assert len([e for e in rows if e["action"] == "PRESENT_ATTESTATION"]) == 1 and "replaced" not in again.state
    # the picture of the refused request is the one of the first attempt, and no picture carries a wrong name
    assert "screens/S6-10_02_clinician_denied_awaiting_trigger.png" in result["evidence"]
    assert "screens/S6-10_04_clinician_granted_after_attestation.png" in result["evidence"]
    assert not [name for name in os.listdir(tmp_path / "screens") if "unexpected" in name]
    # the remark column says that the scenario was continued, and what was taken from the ledger
    row = [r for r in tool.summary_rows(listed.scenarios, again.state["results"]) if r["scenario"] == "S6-10"][0]
    assert row["result"] == "PASS" and "was run again after an attempt that broke off (TimeoutError: the page did not come to rest)" in row["remark"]
    assert "the request on KTRG was not made a second time" in row["remark"] and "the attestation was not made a second time" in row["remark"]


def test_trigger_scenario_issues_a_new_consent_when_the_old_one_cannot_show_it_any_more(tool, listed, tmp_path):
    rows, waiting = [], {}
    first = _continued(tool, listed, tmp_path, rows, waiting=waiting, fail="attest")
    first.run_part(1, "S6-10", "", "s6_10")
    old = first.state["consents"]["KTRG"]
    first.screens.request(old, "did:hospital:001", ["Observation"], "Treatment", "AU")     # two requests after the attestation,
    first.screens.request(old, "did:hospital:001", ["Observation"], "Treatment", "AU")     # made outside the scenario
    again = _continued(tool, listed, tmp_path, rows, waiting=waiting)
    again.run_part(1, "S6-10", "", "s6_10")
    result = again.state["results"]["S6-10"]
    new = again.state["consents"]["KTRG"]
    assert result["result"] == "PASS" and new != old and again.state["replaced"] == {"KTRG": [old]}
    assert again.screens.clicks == ["create", "approve", "approve", "request", "attest", "request"]
    assert [e["result"] for e in rows if e["action"] == "DATA_ACCESS" and e["consent_id"] == new] == ["DENIED", "GRANTED"]
    assert any(f"a new consent KTRG was issued in place of {old[:8]}" in note for note in result["notes"])


def test_screenshot_keeps_the_name_of_its_step_only_when_the_ledger_shows_that_outcome(tool, listed, tmp_path):
    rows = []
    run = _continued(tool, listed, tmp_path, rows)
    run.screens.create = lambda spec, shot_form=None, shot_done=None: "consent-1"       # a consent whose trigger does not wait
    run.run_part(1, "S6-10", "", "s6_10")
    result = run.state["results"]["S6-10"]
    assert result["result"] == "ERROR"
    assert result["message"] == ("RuntimeError: the request on KTRG was GRANTED and the step S6-10_02_clinician_denied_awaiting_trigger "
                                 "expects DENIED. The screenshot is kept as screens/S6-10_02_clinician_denied_awaiting_trigger_unexpected.png.")
    names = os.listdir(tmp_path / "screens")
    assert "S6-10_02_clinician_denied_awaiting_trigger_unexpected.png" in names
    assert "S6-10_02_clinician_denied_awaiting_trigger.png" not in names
    assert "screens/S6-10_02_clinician_denied_awaiting_trigger_unexpected.png" in result["evidence"]
    assert "screens/S6-10_02_clinician_denied_awaiting_trigger.png" not in result["evidence"]
    assert result["observed"]["outcome"] == "GRANTED" and run.screens.clicks[-1] == "request"   # the scenario went no further


def test_request_of_an_attempt_that_broke_off_is_not_made_a_second_time(tool, listed, tmp_path):
    for error in (TimeoutError, KeyboardInterrupt):                   # the page did not answer, or the tool was stopped
        folder = tmp_path / error.__name__
        rows = []
        first = _continued(tool, listed, folder, rows, fail="request", error=error)
        first.state["consents"]["K22"] = "consent-9"
        if error is KeyboardInterrupt:
            with pytest.raises(KeyboardInterrupt):
                first.run_part(1, "S6-01", "", "s6_01")
        else:
            first.run_part(1, "S6-01", "", "s6_01")
            assert first.state["results"]["S6-01"]["result"] == "ERROR"
        assert [e["result"] for e in rows if e["action"] == "DATA_ACCESS"] == ["GRANTED"]       # the release was made and recorded
        again = _continued(tool, listed, folder, rows)
        again.run_part(1, "S6-01", "", "s6_01")
        result = again.state["results"]["S6-01"]
        assert again.screens.clicks == [] and len([e for e in rows if e["action"] == "DATA_ACCESS"]) == 1    # one release, not two
        assert result["result"] == "PASS" and result["transactions"] == ["0x" + "bb" * 32] and result["blocks"] == [11]
        assert any("the request on K22 was not made a second time" in note for note in result["notes"])
        assert any("the tool was stopped while it ran" in note for note in result["notes"]) == (error is KeyboardInterrupt)
        assert set(again.state["added"]["S6-01"]) == {e["event_id"] for e in rows} and "running" not in again.state
        # a later part with the same request is a new request: it is clicked
        again.run_part(1, "S6-16", "", "s6_01")
        assert again.screens.clicks == ["request"]


# ---- the closing evidence --------------------------------------------------------------------------------------------------

def test_closing_makes_the_verification_again_when_the_ledger_has_grown_since_the_last_one(tool, listed, tmp_path):
    rows = [{"event_id": "e1", "consent_id": "c-1", "action": "CREATE_CONSENT", "result": "SUCCESS", "timestamp": "2026-11-17T10:00:00"}]
    verified = []

    def start():
        run = _continued(tool, listed, tmp_path, rows)
        run.state["consents"].update({"L": "c-1", "L2": "c-2"})
        run.screens.audit = lambda consent_id, shot=None: run.screens.shot(shot)
        run.screens.p = SimpleNamespace(get_by_text=lambda text, exact=False: SimpleNamespace(scroll_into_view_if_needed=lambda: None),
                                        screenshot=lambda **kw: None)

        def verify_poc():                                             # stands for the verification tool: it reports what it read
            verified.append(len(rows))
            text = f"Audit ledger: {len(rows)} events\nRESULT: ALL CHECKS PASSED\n"
            with open(run.path("verification", "verify_poc.txt"), "w") as f:
                f.write(text)
            return 0, text
        run.verify_poc = verify_poc
        run.export_chain = lambda ledger: []
        run.write_readme = lambda *a, **kw: None
        return run
    run = start()
    run.close(with_tests=False)
    assert verified == [1] and run.state["results"]["CS-13"]["result"] == "PASS" and run.state["verified_rows"] == 1
    # a scenario is run after the closing, and the closing is made again: the verification covers the new rows
    rows.append({"event_id": "e2", "consent_id": "c-9", "action": "ONCHAIN_MINT", "result": "SUCCESS", "timestamp": "2026-11-17T10:05:00"})
    run = start()
    run.close(with_tests=False)
    assert verified == [1, 2] and run.state["verified_rows"] == 2 and run.state["results"]["CS-13"]["result"] == "PASS"
    assert "Audit ledger: 2 events" in open(tmp_path / "verification" / "verify_poc.txt").read()
    with open(tmp_path / "ledger" / "audit_ledger.json") as f:
        assert len(json.load(f)) == 2                                 # the export and the verification are of the same ledger
    assert any("made again: the ledger holds 2 rows, and the verification before covered 1" in note
               for note in run.state["results"]["CS-13"]["notes"])
    # a closing over the same ledger does not run it a second time
    run = start()
    run.close(with_tests=False)
    assert verified == [1, 2]
    # a verification that fails over the grown ledger is the result of CS-13
    rows.append({"event_id": "e3", "consent_id": "c-9", "action": "ONCHAIN_REVOKE", "result": "SUCCESS", "timestamp": "2026-11-17T10:06:00"})
    run = start()
    run.verify_poc = lambda: (1, "RESULT: SOME CHECKS FAILED\n")
    run.close(with_tests=False)
    assert run.state["results"]["CS-13"]["result"] == "FAIL" and run.state["verified_rows"] == 3


# ---- the end of a start: the test suite, the time source of the decisions -----------------------------------------------

def _closing(tool, listed, folder, rows, suite="467 passed, 4 skipped, 7 warnings in 404.12s (0:06:44) | 404 s"):
    """A start of the tool that makes the closing evidence over the ledger `rows`, with stand-ins for the screens, the
    verification tool, the chain and the test suite (`suite` is its one line)."""
    run = _continued(tool, listed, folder, rows)
    run.state["consents"].update({"L": "c-1", "L2": "c-2"})
    run.screens.audit = lambda consent_id, shot=None: run.screens.shot(shot)
    run.screens.p = SimpleNamespace(get_by_text=lambda text, exact=False: SimpleNamespace(scroll_into_view_if_needed=lambda: None),
                                    screenshot=lambda **kw: None)
    run.verify_poc = lambda: (0, "RESULT: ALL CHECKS PASSED\n")
    run.export_chain = lambda ledger: []
    run.run_tests = lambda: (suite, {})
    run.chain_id, run.sepolia = 5, False
    run.token, run.verifier = SimpleNamespace(address="0x" + "11" * 20), SimpleNamespace(address="0x" + "22" * 20)
    for stage in ("1", "2", "3"):
        run.state["stages"][stage] = {"started": "2026-11-17T10:00:00", "ended": "2026-11-17T11:00:00"}
    return run


def _decision(event_id, action, source, consent_id="c-1"):
    metadata = {"time_source": source} if action == "DATA_ACCESS" else {"time": {"source": source, "unix": 1794909600}}
    return {"event_id": event_id, "consent_id": consent_id, "action": action, "result": "DENIED" if action == "DATA_ACCESS" else "ACTIVE",
            "timestamp": "2026-11-17T10:00:00", "metadata": metadata}


def test_end_of_a_start_names_a_failed_test_suite_and_returns_one(tool, listed, tmp_path):
    assert tool.suite_failed("467 passed, 4 skipped, 7 warnings in 404.12s (0:06:44) | 404 s") is False
    for line in ("1 failed, 466 passed, 4 skipped, 7 warnings in 404.31s (0:06:44) | 405 s", "5 failed, 383 passed, 92 skipped in 211.02s | 211 s",
                 "3 passed, 1 error in 2.11s | 2 s", "2 errors in 1.50s | 2 s", "no result line (exit code 2) | 3 s", "", None):
        assert tool.suite_failed(line) is True
    rows = [_decision("e1", "STATE_CHECK", "block-timestamp"), _decision("e2", "DATA_ACCESS", "block-timestamp")]
    # every scenario passed and one test of the suite failed: the last lines say so, and the exit code is 1
    run = _closing(tool, listed, tmp_path / "failed", rows, suite="1 failed, 466 passed, 4 skipped, 7 warnings in 404.31s (0:06:44) | 405 s")
    counts = dict(run.close(), **{"FAIL": 0, "ERROR": 0})
    said = []
    assert tool.end_of_run(run, counts, 58, closing=True, say=said.append) == 1
    assert said[0].startswith("Scenarios: ") and said[-1] == f"Summary: {tmp_path / 'failed' / 'summary' / 'summary.md'}"
    assert said[1] == ("Automated test suite: 1 failed, 466 passed, 4 skipped, 7 warnings in 404.31s (0:06:44) | 405 s. "
                       "THE SUITE DID NOT PASS: see tests/pytest.txt in the evidence folder.")
    # a suite that gave no result line fails the start as well
    run.state["tests"] = "no result line (exit code 2) | 3 s"
    assert tool.end_of_run(run, counts, 58, closing=True, say=said.append) == 1
    # the same closing with a suite that passed: 0, and the line of the suite is printed
    run = _closing(tool, listed, tmp_path / "passed", rows)
    counts = dict(run.close(), **{"FAIL": 0, "ERROR": 0})
    said = []
    assert tool.end_of_run(run, counts, 58, closing=True, say=said.append) == 0
    assert said[1] == "Automated test suite: 467 passed, 4 skipped, 7 warnings in 404.12s (0:06:44) | 404 s."
    assert said[2] == "Time source of the decisions: the 2 STATE_CHECK and DATA_ACCESS rows of the ledger name the block timestamp."
    # a start that made no closing does not judge the suite, and a failed scenario still gives 1
    said = []
    assert tool.end_of_run(run, counts, 58, closing=False, say=said.append) == 0 and not any("test suite" in line for line in said)
    assert tool.end_of_run(run, dict(counts, FAIL=1), 58, closing=False, say=said.append) == 1


def test_closing_fails_the_run_when_a_decision_was_not_taken_at_the_block_timestamp(tool, listed, tmp_path):
    rows = [_decision("e1aaaaaaaa", "STATE_CHECK", "block-timestamp"), _decision("e2bbbbbbbb", "DATA_ACCESS", "block-timestamp"),
            _decision("e3cccccccc", "STATE_CHECK", "system-clock-fallback", "c-9"), _decision("e4dddddddd", "DATA_ACCESS", "system-clock-fallback", "c-9"),
            _decision("e5eeeeeeee", "DATA_ACCESS", "unavailable", "c-9"),          # refused: the chain could not be read
            {"event_id": "e6", "consent_id": "c-9", "action": "ONCHAIN_MINT", "result": "SUCCESS", "timestamp": "2026-11-17T10:05:00"}]
    run = _closing(tool, listed, tmp_path, rows)
    run.state["added"]["S6-10"] = ["e3cccccccc", "e4dddddddd"]        # the scenario whose steps wrote the two rows
    counts = dict(run.close(), **{"FAIL": 0, "ERROR": 0})
    checked = run.state["time_sources"]
    assert checked["rows"] == 5
    assert [(o["event_id"], o["action"], o["time_source"], o["scenario"]) for o in checked["other"]] == [
        ("e3cccccccc", "STATE_CHECK", "system-clock-fallback", "S6-10"), ("e4dddddddd", "DATA_ACCESS", "system-clock-fallback", "S6-10")]
    line = ("Time source of the decisions: FAILED. 2 of 5 STATE_CHECK and DATA_ACCESS rows name another source than the block "
            "timestamp: STATE_CHECK e3cccccc (S6-10, system-clock-fallback); DATA_ACCESS e4dddddd (S6-10, system-clock-fallback).")
    said = []
    assert tool.end_of_run(run, counts, 58, closing=True, say=said.append) == 1 and line in said     # the suite passed: this alone fails the start
    assert line in open(tmp_path / "README.md").read().splitlines()
    with open(tmp_path / "run_state.json") as f:
        assert json.load(f)["time_sources"] == checked
    # with every decision at the block timestamp the same closing ends with 0
    rows[2:4] = [_decision("e3cccccccc", "STATE_CHECK", "block-timestamp", "c-9"), _decision("e4dddddddd", "DATA_ACCESS", "block-timestamp", "c-9")]
    run = _closing(tool, listed, tmp_path, rows)
    counts = dict(run.close(), **{"FAIL": 0, "ERROR": 0})
    assert run.state["time_sources"] == {"rows": 5, "other": []} and tool.end_of_run(run, counts, 58, closing=True, say=said.append) == 0
    assert "Time source of the decisions: the 5 STATE_CHECK and DATA_ACCESS rows of the ledger name the block timestamp." in open(tmp_path / "README.md").read()


# ---- the machine and the build -------------------------------------------------------------------------------------------

def test_preflight_stops_without_eth_tester_and_when_node_cannot_load_snarkjs(tool, monkeypatch):
    import importlib.metadata
    import sys
    from services import zk_decision_service
    asked = []

    def node(answer):
        def process(args, **options):                                 # stands for node
            asked.append((list(args), options.get("cwd")))
            return SimpleNamespace(returncode=answer, stdout="v20.11.0\n", stderr="Error: Cannot find module 'snarkjs'" if answer else "")
        return process
    monkeypatch.setattr(tool.subprocess, "run", node(0))
    monkeypatch.setitem(sys.modules, "eth_tester", SimpleNamespace())  # stands for the installed package
    tool.check_machine()                                              # both are there: nothing is said
    assert asked == [(["node", "-e", "require('snarkjs')"], os.path.join(ROOT, "zk"))]
    found = tool.versions()
    assert list(found) == ["streamlit", "web3", "playwright", "eth-tester", "node"] and found["node"] == "v20.11.0"
    assert found["streamlit"] == importlib.metadata.version("streamlit") and tool.MADE_WITH_STREAMLIT == "1.67.0"
    # node cannot load snarkjs: the three files of the circuit are there, and still no proof could be made
    monkeypatch.setattr(tool.subprocess, "run", node(1))
    with pytest.raises(tool.Stop) as stopped:
        tool.check_machine()
    assert str(stopped.value) == ("node cannot load snarkjs in zk/ (zk/node_modules is not in the repository): "
                                  "cd zk && npm install snarkjs@0.7.4.")
    # eth-tester is not installed
    monkeypatch.setattr(tool.subprocess, "run", node(0))
    monkeypatch.setitem(sys.modules, "eth_tester", None)              # the import fails, as without the package
    with pytest.raises(tool.Stop) as stopped:
        tool.check_machine()
    assert str(stopped.value) == ("eth-tester is not installed: the suite of the closing evidence would skip most on-chain tests "
                                  'and fail five. pip install "eth-tester[py-evm]".')
    # the preflight makes this check after it has found the circuit and before it reads the contracts, and its
    # first line names the versions
    monkeypatch.setattr(zk_decision_service, "decision_available", lambda depth=16: True)
    for name in ("CONTRACT_V4_ADDRESS", "VERIFIER_ADDRESS", "POSEIDON_ADDRESS", "GROTH16_VERIFIER_ADDRESS"):
        monkeypatch.setenv(name, "0x" + "11" * 20)
    monkeypatch.setenv("CHAIN_ID", "5")
    run = SimpleNamespace(chain_id=5, sepolia=False, w3=SimpleNamespace(eth=SimpleNamespace(block_number=7)))
    with pytest.raises(tool.Stop, match="eth-tester is not installed"):
        tool.preflight(run, "0x" + "22" * 20, 1)
    monkeypatch.setitem(sys.modules, "eth_tester", SimpleNamespace())
    monkeypatch.setattr(tool, "check_machine", lambda: (_ for _ in ()).throw(tool.Stop("the machine was checked")))
    said = []
    monkeypatch.setattr(tool, "versions", lambda: said.append("versions") or {"streamlit": "1.67.0", "node": "v20.11.0"})
    with pytest.raises(tool.Stop, match="the machine was checked"):
        tool.preflight(run, "0x" + "22" * 20, 1)
    assert said == ["versions"]


def test_multiselect_of_another_streamlit_stops_the_run_and_names_the_version(tool, listed, tmp_path, monkeypatch):
    from tools.final_run_screens import Screens
    asked = []

    def page(found):                                                  # stands for the page of the browser
        return SimpleNamespace(locator=lambda selector: asked.append(selector) or SimpleNamespace(count=lambda: found))
    screens = Screens(page(1), "http://127.0.0.1:1", str(tmp_path))
    screens.open = lambda role="Patient": asked.append(role)
    # the first page is the Patient screen, and the element looked for is the one the scope fields are read through
    assert screens.drives_multiselect() is True and asked == ["Patient", '[data-testid="stMultiSelect"] .react-aria-ComboBox']
    screens.p = page(0)
    assert screens.drives_multiselect() is False
    run = _run(tool, listed, tmp_path)
    run.screens = screens
    monkeypatch.setattr(tool, "versions", lambda: {"streamlit": "1.70.2"})
    with pytest.raises(tool.Stop) as stopped:
        run.check_screens()
    assert str(stopped.value) == ("The multiselect of Streamlit 1.70.2 is not the one this tool drives (made with 1.67.0): "
                                  "pip install streamlit==1.67.0.")
    screens.p = page(1)
    run.check_screens()                                               # the multiselect of the rehearsal: the run goes on


def test_build_is_noted_at_the_first_start_and_a_later_start_on_changed_files_stops(tool, listed, tmp_path):
    root = tmp_path / "repository"
    for name, text in (("app.py", "page = 1\n"), ("services/request_service.py", "a = 1\n"), ("blockchain/abi/ConsentSBTv4.json", "{}\n"),
                       ("tools/final_run.py", "b = 1\n"), ("services/__pycache__/request_service.cpython-311.pyc", "x"),
                       ("tests/test_a.py", "c = 1\n"), ("README.md", "notes\n")):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    first = tool.build_identity(str(root))
    assert sorted(first["files"]) == ["app.py", "blockchain/abi/ConsentSBTv4.json", "services/request_service.py", "tools/final_run.py"]
    assert len(first["checksum"]) == 64 and tool.build_identity(str(root))["checksum"] == first["checksum"]
    run = _run(tool, listed, tmp_path / "run")
    assert run.check_build("start of stage 1", root=str(root)) == [] and run.state["build"] == first
    with open(tmp_path / "run" / "run_state.json") as f:
        assert json.load(f)["build"]["files"] == first["files"]       # kept with the run
    # a later start on the same files, and files outside the build that changed: nothing to say
    (root / "README.md").write_text("other notes\n")
    (root / "services" / "__pycache__" / "request_service.cpython-311.pyc").write_text("y")
    again = _run(tool, listed, tmp_path / "run")
    assert again.check_build("start of stage 2", root=str(root)) == [] and "build_changes" not in again.state
    # an edit of the application and a new service file between two stages: the next start stops and names them
    (root / "app.py").write_text("page = 2\n")
    (root / "services" / "new_service.py").write_text("d = 1\n")
    with pytest.raises(tool.Stop) as stopped:
        again.check_build("start of stage 2", root=str(root))
    assert "The files of the build have changed since the first start of this run (app.py (changed), services/new_service.py (new))" in str(stopped.value)
    assert "--accept-build-change" in str(stopped.value) and not again.state.get("build_changes")
    # accepted: the run goes on, and the difference is kept for README.md
    assert again.check_build("start of stage 2", accept=True, root=str(root)) == ["app.py (changed)", "services/new_service.py (new)"]
    (change,) = again.state["build_changes"]
    assert (change["when"], change["files"], change["accepted"]) == ("start of stage 2", ["app.py (changed)", "services/new_service.py (new)"], True)
    assert change["checksum"] != first["checksum"] and again.state["build"] == first
    third = _run(tool, listed, tmp_path / "run")
    assert third.check_build("start of stage 3", root=str(root)) and len(third.state["build_changes"]) == 1    # the accepted build is not asked for again
    # files that change while a stage runs are found at the closing, which does not stop: README.md names them
    (root / "tools" / "final_run.py").write_text("b = 2\n")
    assert third.check_build("closing", root=str(root)) == ["app.py (changed)", "services/new_service.py (new)", "tools/final_run.py (changed)"]
    assert [(c["when"], c["accepted"]) for c in third.state["build_changes"]] == [("start of stage 2", True), ("closing", False)]
    third.chain_id, third.sepolia = 5, False
    third.token, third.verifier = SimpleNamespace(address="0x" + "11" * 20), SimpleNamespace(address="0x" + "22" * 20)
    third.write_readme()
    text = open(tmp_path / "run" / "README.md").read()
    assert f"Build at the first start: commit {first['commit']}, checksum {first['checksum'][:12]} of 4 files" in text
    assert "THE BUILD CHANGED DURING THE RUN. This folder holds the work of more than one build:" in text
    assert "(start of stage 2): " in text and "Files that differ from the first start: app.py (changed), services/new_service.py (new). Accepted at that start." in text
    assert "(closing): " in text and "tools/final_run.py (changed)." in text
    said = []
    tool.end_of_run(third, {"PASS": 58, "FAIL": 0, "ERROR": 0, "NOT RUN": 0}, 58, say=said.append)
    assert sum(line.startswith("The build changed during the run (") for line in said) == 2
    # a start after the closing found the change stops again: that build was never accepted
    with pytest.raises(tool.Stop):
        _run(tool, listed, tmp_path / "run").check_build("start of stage close", root=str(root))
    # a run whose files never changed says so
    clean = _run(tool, listed, tmp_path / "clean")
    clean.check_build("start of stage 1", root=str(root))
    clean.chain_id, clean.sepolia, clean.token, clean.verifier = 5, False, third.token, third.verifier
    clean.write_readme()
    assert "The files of the build were the same at every start so far." in open(tmp_path / "clean" / "README.md").read()


def test_build_of_this_repository_covers_the_files_the_application_and_the_tool_execute(tool):
    build = tool.build_identity()
    for name in ("app.py", "halah_theme.py", "services/request_service.py", "services/revocation_service.py", "blockchain/deploy_v4.py",
                 "blockchain/abi/ConsentSBTv4.json", "blockchain/abi/HalahDecisionVerifier.json", "database/consent_db.py", "models/consent.py",
                 "zk/prove_decision.js", "data/credentials/demo_credentials.json", "tools/final_run.py", "tools/final_run_screens.py",
                 "tools/final_run_scenarios.json", "tools/verify_poc.py"):
        assert name in build["files"], name
    assert not [name for name in build["files"] if "__pycache__" in name or name.startswith(("tests/", "zk/build", "zk/node_modules", "evidence/"))]


# ---- the summary: the reason of a refusal ---------------------------------------------------------------------------------

def test_summary_names_the_reason_of_a_refusal_in_the_decision_columns(tool, listed, tmp_path):
    results = {"S7-08": {"result": "PASS", "observed": {"outcome": "REJECTED", "reason_text": "tag already seen"}},
               "S7-09": {"result": "FAIL", "observed": {"outcome": "REJECTED", "reason_text": "proof is not valid"},
                         "differences": ["reason_text: observed 'proof is not valid', expected 'time is too old'"]},
               "S7-02": {"result": "PASS", "observed": {"outcome": "NO PROOF", "failed_predicates": ["WINDOW"], "circuit_refused": True}},
               "S6-13": {"result": "PASS", "observed": {"outcome": "REFUSED", "reason": "GUARDIAN-AFTER-MAJORITY", "reason_on_reissue": "FORMER-GUARDIAN",
                                                        "successor_state": "ACTIVE"}},
               "S6-03": {"result": "PASS", "observed": {"outcome": "DENIED", "deny_code": "OUT-OF-SCOPE", "failed_checks": ["VP"], "state": "ACTIVE"}}}
    row = {r["scenario"]: r for r in tool.summary_rows(listed.scenarios, results)}
    # the four refusals of the verifier contract no longer look alike: each row expects another reason
    assert [row[s]["expected decision"] for s in ("S7-07", "S7-08", "S7-09", "S7-10")] == [
        "REJECTED (proof is not valid)", "REJECTED (tag already seen)", "REJECTED (time is too old)", "REJECTED (revocation root is not current)"]
    assert row["S7-08"]["observed decision"] == "REJECTED (tag already seen)" == row["S7-08"]["expected decision"]
    assert row["S7-09"]["observed decision"] == "REJECTED (proof is not valid)" != row["S7-09"]["expected decision"]
    assert row["S7-02"]["expected decision"] == row["S7-02"]["observed decision"] == "NO PROOF (WINDOW)"
    assert row["S6-13"]["expected decision"] == row["S6-13"]["observed decision"] == "REFUSED (GUARDIAN-AFTER-MAJORITY; on the re-issue: FORMER-GUARDIAN)"
    assert row["S5-08"]["expected decision"] == "REFUSED (Ownable: caller is not the owner)" and row["S5-10"]["expected decision"] == "REFUSED (Soulbound Token)"
    assert row["S5-11"]["expected decision"] == "REFUSED (CREDENTIAL_REVOKED)" and row["CS-12"]["expected decision"] == "REJECTED (new proof: NO PROOF)"
    # a request that is denied keeps its plain decision: its code has its own column, which holds one of the nine or nothing
    assert (row["S6-03"]["expected decision"], row["S6-03"]["observed decision"], row["S6-03"]["observed deny code"]) == ("DENIED", "DENIED", "OUT-OF-SCOPE")
    assert all(r["expected deny code"] in NINE + ("",) and r["observed deny code"] in NINE + ("",) for r in row.values())
    assert row["S7-01"]["observed decision"] == "" and row["S6-01"]["expected decision"] == "GRANTED"
    # every scenario that expects a reason which is not a deny code shows it
    reasoned = [s["id"] for s in listed.scenarios if any(k in s["expected_check"] for k in ("reason_text", "failed_predicates", "reason", "approval_reason", "new_proof"))]
    assert len(reasoned) == 16 and all("(" in row[i]["expected decision"] for i in reasoned)
    tool.write_summary(str(tmp_path), listed.scenarios, results)
    text = open(tmp_path / "summary.md").read()
    assert "| REJECTED (tag already seen) |  | REJECTED (tag already seen) |" in text and "REJECTED (time is too old)" in open(tmp_path / "summary.csv").read()
