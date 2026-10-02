"""Small offline pilot. No cloud calls, hidden optimizers, or production leaderboard."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASIS = {"rz", "sx", "x", "cx"}
SEEDS = [7, 19, 43]
REPEATS = 3
SUITE = "pilot-v0.2"
QASMBENCH_REVISION = "357b942396d5c2b7cbc1c229c585a6ef5ccaebac"
CORPUS_CASES = {
    "qft_n4": "QFT",
    "qaoa_n3": "QAOA",
    "adder_n4": "Adder",
    "grover_n2": "Grover",
    "vqe_n4": "VQE",
    "ising_n10": "Hamiltonian",
}


def edges_for(n: int, target: str) -> list[tuple[int, int]]:
    if target not in {"all-to-all", "line"}:
        raise ValueError(target)
    return [
        (a, b)
        for a in range(n)
        for b in range(n)
        if a != b and (target == "all-to-all" or abs(a - b) == 1)
    ]


def metrics(circuit, edges: list[tuple[int, int]]) -> dict:
    """One shared dependency-DAG metric, independent of SDK moment definitions."""
    two_depth = [0] * circuit.num_qubits
    total_depth = [0] * circuit.num_qubits
    counts: dict[str, int] = {}
    for item in circuit.data:
        name = item.operation.name
        qubits = [circuit.find_bit(q).index for q in item.qubits]
        if name not in BASIS:
            raise ValueError(f"Unexpected output gate: {name}")
        if len(qubits) != (2 if name == "cx" else 1):
            raise ValueError(f"Invalid gate arity: {name}")
        if name == "cx" and tuple(qubits) not in edges:
            raise ValueError(f"Invalid coupling: {qubits}")
        counts[name] = counts.get(name, 0) + 1
        d2 = max(two_depth[q] for q in qubits) + (len(qubits) == 2)
        dt = max(total_depth[q] for q in qubits) + 1
        for q in qubits:
            two_depth[q] = d2
            total_depth[q] = dt
    return {
        "two_qubit_count": counts.get("cx", 0),
        "two_qubit_depth": max(two_depth, default=0),
        "total_depth": max(total_depth, default=0),
        "one_qubit_count": sum(v for k, v in counts.items() if k != "cx"),
        "gate_counts": counts,
    }


def validation_copy(circuit, initial: list[int], final: list[int]):
    """Restore input labeling and encode final logical ordering as measurements."""
    from qiskit import QuantumCircuit

    n = circuit.num_qubits
    if sorted(initial) != list(range(n)) or sorted(final) != list(range(n)):
        raise ValueError("Pilot requires bijective maps, with no added workspace")
    inverse = {physical: logical for logical, physical in enumerate(initial)}
    checked = QuantumCircuit(n, n)
    checked.global_phase = circuit.global_phase
    for item in circuit.data:
        checked.append(
            item.operation,
            [inverse[circuit.find_bit(q).index] for q in item.qubits],
        )
    for logical, physical in enumerate(final):
        checked.measure(inverse[physical], logical)
    return checked


def check_equivalence(original, native, initial: list[int], final: list[int]) -> dict:
    from mqt import qcec

    before = original.copy()
    before.measure_all()
    after = validation_copy(native, initial, final)
    result = qcec.verify(
        before,
        after,
        run_simulation_checker=False,
        run_zx_checker=False,
        parallel=False,
        nthreads=1,
        timeout=20,
    )
    details = result.json()
    if isinstance(details, str):
        details = json.loads(details)
    # Simulation-only "probably equivalent" is deliberately not accepted.
    accepted = result.equivalence.name in {"equivalent", "equivalent_up_to_global_phase"}
    return {"accepted": accepted, "criterion": result.equivalence.name, "details": details}


def corpus_unitary(path: Path):
    """Keep preparation/gates; remove barriers and per-wire terminal readout only."""
    from qiskit import QuantumCircuit, qasm2

    source = qasm2.load(path, custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS)
    unitary = QuantumCircuit(*source.qregs)
    measured = set()
    removed = {"measure": 0, "barrier": 0}
    for item in source.data:
        name = item.operation.name
        if name == "barrier":
            removed[name] += 1
            continue
        if name == "measure":
            measured.update(item.qubits)
            removed[name] += 1
            continue
        if item.clbits or name == "reset" or getattr(item.operation, "condition", None):
            raise ValueError("Dynamic/nonunitary corpus input is unsupported")
        if measured.intersection(item.qubits):
            raise ValueError("Measurement is not terminal on its wire")
        unitary.append(item.operation, item.qubits)
    return unitary, removed


def generate_inputs() -> list[dict]:
    from qiskit import QuantumCircuit, qasm2, transpile
    from qiskit.circuit.library import CDKMRippleCarryAdder

    folder = ROOT / "data" / "inputs"
    folder.mkdir(parents=True, exist_ok=True)
    cases = []
    for family in ["QFT", "QAOA", "Adder"]:
        for size in [4, 6] if family != "Adder" else [2, 3]:
            parameters = {}
            if family == "QFT":
                qc = QuantumCircuit(size)
                for j in reversed(range(size)):
                    qc.h(j)
                    for k in reversed(range(j)):
                        qc.cp(math.pi / 2 ** (j - k), j, k)
                for j in range(size // 2):
                    qc.swap(j, size - j - 1)
                parameters = {"variant": "exact QFT, including output reversal"}
            elif family == "QAOA":
                qc = QuantumCircuit(size)
                graph = [(i, (i + 1) % size) for i in range(size)]
                graph += [(0, size // 2)]
                gammas, betas = [0.37, 0.61], [0.23, 0.49]
                qc.h(range(size))
                for gamma, beta in zip(gammas, betas, strict=True):
                    for a, b in graph:
                        qc.cx(a, b)
                        qc.rz(2 * gamma, b)
                        qc.cx(a, b)
                    for i in range(size):
                        qc.rx(2 * beta, i)
                parameters = {"graph": graph, "p": 2, "gamma": gammas, "beta": betas}
            else:
                qc = CDKMRippleCarryAdder(size, kind="full").decompose()
                parameters = {"register_bits": size, "kind": "full CDKM ripple-carry"}
            # Frozen low-level input track: lowering only, no optimization or mapping.
            qc = transpile(qc, basis_gates=["h", "x", "rx", "ry", "rz", "cx"], optimization_level=0)
            name = f"{family.lower()}-{qc.num_qubits}q"
            qasm = qasm2.dumps(qc) + "\n"
            path = folder / f"{name}.qasm"
            path.write_text(qasm)
            cases.append(
                {
                    "id": name,
                    "family": family,
                    "qubits": qc.num_qubits,
                    "parameters": parameters,
                    "path": str(path.relative_to(ROOT)),
                    "sha256": hashlib.sha256(qasm.encode()).hexdigest(),
                    "input_gate_count": len(qc.data),
                }
            )
    for source_id, family in CORPUS_CASES.items():
        source = ROOT / "corpora" / "qasmbench" / f"{source_id}.qasm"
        qc, removed = corpus_unitary(source)
        qc = transpile(qc, basis_gates=["h", "x", "rx", "ry", "rz", "cx"], optimization_level=0)
        name = f"qasmbench-{source_id}"
        qasm = qasm2.dumps(qc) + "\n"
        path = folder / f"{name}.qasm"
        path.write_text(qasm)
        cases.append(
            {
                "id": name,
                "family": family,
                "qubits": qc.num_qubits,
                "parameters": {"variant": source_id, "removed_instructions": removed},
                "provenance": {
                    "corpus": "QASMBench",
                    "revision": QASMBENCH_REVISION,
                    "url": f"https://github.com/pnnl/QASMBench/blob/{QASMBENCH_REVISION}/small/{source_id}/{source_id}.qasm",
                    "source_path": str(source.relative_to(ROOT)),
                    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "license_path": "corpora/qasmbench/LICENSE",
                    "transformation": (
                        "remove barriers and per-wire terminal measurements; "
                        "retain preparation; Qiskit level-0 lowering"
                    ),
                },
                "path": str(path.relative_to(ROOT)),
                "sha256": hashlib.sha256(qasm.encode()).hexdigest(),
                "input_gate_count": len(qc.data),
            }
        )
    return cases


def compile_once(original, compiler: str, target: str, seed: int):
    from qiskit import qasm2

    n = original.num_qubits
    edges = edges_for(n, target)
    if compiler == "qiskit":
        from qiskit.transpiler import CouplingMap
        from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

        start = time.perf_counter_ns()
        pm = generate_preset_pass_manager(
            optimization_level=2,
            basis_gates=sorted(BASIS),
            coupling_map=CouplingMap(edges),
            seed_transpiler=seed,
            approximation_degree=1.0,
        )
        native = pm.run(original)
        elapsed = (time.perf_counter_ns() - start) / 1e6
        initial = native.layout.initial_index_layout(filter_ancillas=True)
        final = native.layout.final_index_layout(filter_ancillas=True)
    elif compiler == "pytket":
        from pytket.architecture import Architecture
        from pytket.circuit import OpType, Qubit
        from pytket.extensions.qiskit import tk_to_qiskit
        from pytket.passes import (
            AutoRebase,
            DefaultMappingPass,
            FullPeepholeOptimise,
            SequencePass,
            SynthesiseTket,
        )
        from pytket.predicates import CompilationUnit
        from pytket.qasm import circuit_from_qasm_str

        # Parse is intentionally outside the compile timer, for both SDKs.
        tkc = circuit_from_qasm_str(qasm2.dumps(original))
        # tket sorts registers by name; Qiskit preserves declaration order.
        # Interpret maps in input-wire order, not the parser's sorted order.
        logical_qubits = [
            Qubit(register.name, index)
            for register in original.qregs
            for index in range(register.size)
        ]
        start = time.perf_counter_ns()
        unit = CompilationUnit(tkc)
        pipeline = SequencePass(
            [
                FullPeepholeOptimise(allow_swaps=False),
                DefaultMappingPass(Architecture(edges)),
                SynthesiseTket(),
                AutoRebase({OpType.Rz, OpType.SX, OpType.X, OpType.CX}, allow_swaps=False),
            ]
        )
        pipeline.apply(unit)
        elapsed = (time.perf_counter_ns() - start) / 1e6
        physical = list(unit.circuit.qubits)
        initial = [physical.index(unit.initial_map[q]) for q in logical_qubits]
        final = [physical.index(unit.final_map[q]) for q in logical_qubits]
        native = tk_to_qiskit(unit.circuit, replace_implicit_swaps=False, perm_warning=False)
    else:
        raise ValueError(compiler)
    return native, elapsed, initial, final


def worker(case: dict, compiler: str, target: str, seed: int) -> dict:
    from qiskit import qasm2

    original = qasm2.load(ROOT / case["path"])
    timings = []
    trials = []
    for _ in range(REPEATS):
        native, elapsed, initial, final = compile_once(original, compiler, target, seed)
        timings.append(elapsed)
        trials.append(
            {
                "metrics": metrics(native, edges_for(case["qubits"], target)),
                "validation": check_equivalence(original, native, initial, final),
                "initial_map": initial,
                "final_map": final,
                "qasm": qasm2.dumps(native),
            }
        )
    output_dir = ROOT / "data" / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for i, trial in enumerate(trials):
        filename = f"{case['id']}-{target}-{compiler}-s{seed}-r{i}.qasm"
        path = output_dir / filename
        path.write_text(trial.pop("qasm") + "\n")
        trial["artifact"] = str(path.relative_to(ROOT))
        artifacts.append(trial)
    valid = all(t["validation"]["accepted"] for t in trials)
    return {
        "case_id": case["id"],
        "family": case["family"],
        "qubits": case["qubits"],
        "compiler": compiler,
        "target": target,
        "seed": seed,
        "seed_supported": compiler == "qiskit",
        "status": "passed" if valid else "verification_failed",
        "compile_ms": statistics.median(timings),
        "timing_samples_ms": timings,
        "metrics": {
            key: statistics.median(t["metrics"][key] for t in trials)
            for key in ["two_qubit_count", "two_qubit_depth", "total_depth", "one_qubit_count"]
        },
        "trials": artifacts,
    }


def run_pilot(*, overwrite: bool = False) -> None:
    results_path = ROOT / "data" / "results.json"
    if results_path.exists():
        previous = json.loads(results_path.read_text())
        if previous["suite"] != SUITE:
            archive = ROOT / "releases" / previous["suite"] / "data" / "results.json"
            if not archive.exists() or archive.read_bytes() != results_path.read_bytes():
                raise RuntimeError("Archive the existing release before changing suites")
        elif not overwrite:
            raise RuntimeError(
                "Results already exist; use --overwrite to explicitly rerun this suite"
            )
    if not hasattr(os, "sched_setaffinity"):
        raise RuntimeError("This pilot requires Linux CPU affinity")
    allowed = sorted(os.sched_getaffinity(0))
    selected = allowed[0]
    os.sched_setaffinity(0, {selected})
    cases = generate_inputs()
    (ROOT / "data" / "manifest.json").write_text(
        json.dumps(cases, indent=2, ensure_ascii=False) + "\n"
    )
    jobs = [
        (case, compiler, target, seed)
        for case in cases
        for compiler in ["qiskit", "pytket"]
        for target in ["all-to-all", "line"]
        for seed in SEEDS
    ]
    random.Random(20261002).shuffle(jobs)
    env = dict(os.environ)
    env.update(
        {
            k: "1"
            for k in [
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "RAYON_NUM_THREADS",
                "QISKIT_NUM_PROCS",
            ]
        }
    )
    results = []
    for case, compiler, target, seed in jobs:
        command = [
            sys.executable,
            str(ROOT / "atlas.py"),
            "worker",
            case["id"],
            compiler,
            target,
            str(seed),
        ]
        try:
            execution = subprocess.run(
                command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120
            )
            if execution.returncode:
                raise RuntimeError(execution.stderr[-4000:])
            result = json.loads(execution.stdout)
        except subprocess.TimeoutExpired:
            result = {"status": "timeout", "error": "120 s worker budget exceeded"}
        except (RuntimeError, json.JSONDecodeError) as error:
            result = {"status": "error", "error": str(error)}
        result.update(
            case_id=case["id"],
            family=case["family"],
            qubits=case["qubits"],
            compiler=compiler,
            target=target,
            seed=seed,
        )
        results.append(result)
        print(f"{len(results):02}/{len(jobs)} {case['id']} {compiler} {target} {result['status']}")
    cpu = next(
        (
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name")
        ),
        "unknown",
    )
    document = {
        "schema_version": 1,
        "suite": SUITE,
        "created_at": datetime.now(UTC).isoformat(),
        "formal_ranking": False,
        "environment": {
            "cpu": cpu,
            "cpu_affinity": [selected],
            "platform": platform.platform(),
            "python": platform.python_version(),
            "thread_env": {
                k: env[k]
                for k in env
                if k
                in {
                    "OMP_NUM_THREADS",
                    "OPENBLAS_NUM_THREADS",
                    "MKL_NUM_THREADS",
                    "RAYON_NUM_THREADS",
                    "QISKIT_NUM_PROCS",
                }
            },
            "versions": {
                p: importlib.metadata.version(p)
                for p in ["qiskit", "pytket", "pytket-qiskit", "mqt.qcec"]
            },
            "exclusive_machine": False,
            "memory_limit_enforced": False,
        },
        "protocol": {
            "seeds": SEEDS,
            "timing_repeats": REPEATS,
            "worker_timeout_seconds": 120,
            "basis": sorted(BASIS),
            "physical_qubits": "equal to input width",
            "timer": "pipeline construction + compilation; excludes parse, export, validation",
            "cold_worker": True,
            "input_track": "Qiskit level-0 lowered common OpenQASM 2; not high-level track",
            "pytket_pipeline": [
                "FullPeepholeOptimise(allow_swaps=False)",
                "DefaultMappingPass(GraphPlacement)",
                "SynthesiseTket",
                "AutoRebase(rz,sx,x,cx)",
            ],
            "qiskit_pipeline": "preset level 2, approximation_degree=1.0",
            "validation": "QCEC decision diagrams, no simulation/ZX, 20 s verification timeout",
        },
        "cases": cases,
        "results": results,
    }
    (ROOT / "data" / "results.json").write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["run", "worker"])
    parser.add_argument("args", nargs="*")
    parser.add_argument("--overwrite", action="store_true")
    options = parser.parse_args()
    if options.action == "run":
        run_pilot(overwrite=options.overwrite)
    else:
        case_id, compiler, target, seed = options.args
        manifest = json.loads((ROOT / "data" / "manifest.json").read_text())
        case = next(c for c in manifest if c["id"] == case_id)
        print(json.dumps(worker(case, compiler, target, int(seed))))


if __name__ == "__main__":
    main()
