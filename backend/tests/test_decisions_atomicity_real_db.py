"""AT-3 / AT-4 (docs/memory-design.md section 7.3): two independent OS processes.

Opt-in: RUN_LIVE_FALKORDB_TESTS=1. Each test launches two separate Python
interpreters (subprocess), each with its own FalkorDB connection, firing the
same operation at a shared scheduled instant for ROUNDS rounds. Pass = every
round correct. Results are evidence for this FalkorDB image and these operations only.
"""
import json
import os
import statistics
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import load_dotenv

from relaymind.contracts.models import TrustedContext
from relaymind.graph import access
from relaymind.graph.access import authorized_graph
from relaymind.graph.connection import create_client
from relaymind.memory.decisions import get_current_decisions, record_decision, record_source

load_dotenv()
pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_FALKORDB_TESTS") != "1",
                                reason="Opt-in live FalkorDB tests")
ROUNDS = int(os.getenv("ATOMICITY_ROUNDS", "100"))
SPACING = 0.4
MAX_SKEW_MS = 25  # rounds whose two operations start further apart did not really race
WORKER = Path(__file__).with_name("atomicity_worker.py")
CTX = TrustedContext(tenant_id="demo-a", user_id="developer-a")


@pytest.fixture
def project(monkeypatch):
    pid = "atest-" + uuid4().hex[:12]
    monkeypatch.setitem(access._DEMO_ACCESS, ("demo-a", "developer-a"),
                        ("relaymind_demo_a", frozenset({"launch-01", pid})))
    client = create_client()
    graph = authorized_graph(client, CTX, pid)
    graph.query("CREATE (:Project {id: $id, name: 'atomicity test'})", params={"id": pid})
    record_source(client, CTX, pid, f"{pid}-src", "note", "src", "synthetic")
    yield client, graph, pid
    graph.query("MATCH (n) WHERE n.project_id = $id DETACH DELETE n", params={"id": pid})
    graph.query("MATCH (p:Project {id: $id}) DETACH DELETE p", params={"id": pid})


def race(mode, pid):
    cfg = {"mode": mode, "project": pid, "rounds": ROUNDS, "spacing": SPACING}
    procs = [subprocess.Popen(
        [sys.executable, str(WORKER), json.dumps(cfg | {"worker": w})],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for w in ("w1", "w2")]
    for p in procs:  # barrier: both interpreters imported and connected
        ready = p.stdout.readline().strip()
        assert ready == "READY", p.stderr.read()[-2000:]
    start = time.time() + 1.0
    for p in procs:
        p.stdin.write(f"{start}\n")
        p.stdin.flush()
    # Drain both workers concurrently: reading one to completion first lets the
    # other block on a full stdout pipe (small on Windows) and fall out of sync.
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda p: p.communicate(timeout=60 + ROUNDS * SPACING), procs))
    lines = []
    for p, (out, err) in zip(procs, results):
        assert p.returncode == 0, err[-2000:]
        lines += [json.loads(line) for line in out.splitlines() if line.strip()]
    rounds = {}
    for line in lines:
        rounds.setdefault(line["round"], {})[line["worker"]] = line
    assert len(rounds) == ROUNDS and all(len(r) == 2 for r in rounds.values())
    skew = [abs(r["w1"]["fired_at"] - r["w2"]["fired_at"]) * 1000 for r in rounds.values()]
    print(f"\n{mode}: {ROUNDS} rounds, fire skew ms median={statistics.median(skew):.2f} max={max(skew):.2f}")
    assert max(skew) <= MAX_SKEW_MS, "workers did not fire together; result would not be evidence"
    return rounds


def test_at3_concurrent_identical_create_yields_one_decision(project):
    client, graph, pid = project
    rounds = race("AT-3", pid)
    bad = []
    for rnd, r in rounds.items():
        nodes = graph.ro_query("MATCH (d:Decision {id: $id}) RETURN count(d)",
                               params={"id": f"{pid}-same-{rnd}"}).result_set[0][0]
        outcomes = sorted(x["outcome"] for x in r.values())
        if nodes != 1 or outcomes != ["ok", "ok"]:
            bad.append((rnd, nodes, outcomes))
    print(f"AT-3 incorrect rounds: {len(bad)}/{ROUNDS} {bad[:5]}")
    assert not bad


def test_at4_concurrent_supersede_of_same_decision_has_one_winner(project):
    client, graph, pid = project
    for rnd in range(ROUNDS):
        record_decision(client, CTX, pid, f"{pid}-base-{rnd}", f"t{rnd}", "base",
                        [f"{pid}-src"], human_approved=True)
    rounds = race("AT-4", pid)
    state = get_current_decisions(client, CTX, pid)
    current_by_topic = {}
    for d in state.current + state.conflicting:
        current_by_topic.setdefault(d.topic, []).append(d.id)
    bad = []
    for rnd, r in rounds.items():
        outcomes = sorted(x["outcome"] for x in r.values())
        current = current_by_topic.get(f"t{rnd}", [])
        if outcomes != ["InvalidSupersessionError", "ok"] or len(current) != 1:
            bad.append((rnd, outcomes, current))
    print(f"AT-4 incorrect rounds: {len(bad)}/{ROUNDS} {bad[:5]}")
    assert not bad
