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
import signal
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from cirq_adapter import recipe_metadata as cirq_recipe_metadata
from qmap_adapter import recipe_metadata

ROOT = Path(__file__).resolve().parent
BASIS = {"rz", "sx", "x", "cx"}
SEEDS = [7, 19, 43]
REPEATS = 3
SUITE = "pilot-v0.6-cirq-mixed-budgets"
MEASUREMENT_SUITE = "pilot-cirq-routecqc-v1-420s"
COMPILERS = ["qiskit", "pytket", "bqskit", "qmap", "cirq"]
SDK_PACKAGES = {
    "qiskit": "qiskit",
    "pytket": "pytket",
    "bqskit": "bqskit",
    "qmap": "mqt.qmap",
    "cirq": "cirq-core",
}
BQSKIT_EPSILON = 1e-12
WORKER_TIMEOUT_SECONDS = 420
REFERENCE_CONFIGURATION = "qiskit-l2"
CONFIGURATIONS = [
    *[
        {
            "id": f"qiskit-l{level}",
            "compiler": "qiskit",
            "label": f"Level {level}",
            "optimization_level": level,
            "seed_supported": True,
        }
        for level in range(4)
    ],
    {
        "id": "pytket-basic",
        "compiler": "pytket",
        "label": "Basic synthesis",
        "recipe": "basic",
        "seed_supported": False,
    },
    {
        "id": "pytket-peephole",
        "compiler": "pytket",
        "label": "Peephole",
        "recipe": "peephole",
        "seed_supported": False,
    },
    {
        "id": "pytket-pauli",
        "compiler": "pytket",
        "label": "Pauli + peephole",
        "recipe": "pauli",
        "seed_supported": True,
    },
    *[
        {
            "id": f"bqskit-l{level}",
            "compiler": "bqskit",
            "label": f"Level {level} · 2Q blocks",
            "optimization_level": level,
            "seed_supported": True,
        }
        for level in range(1, 5)
    ],
    {
        "id": "qmap-sc-heuristic-maponly-v1",
        "compiler": "qmap",
        "label": "Heuristic mapping + native lowering",
        "seed_supported": False,
        "recipe": recipe_metadata(),
    },
]


CONFIGURATIONS.append(
    {
        "id": "cirq-routecqc-maponly-v1",
        "compiler": "cirq",
        "label": "RouteCQC mapping + native lowering",
        "seed_supported": False,
        "recipe": cirq_recipe_metadata(),
    }
)
MEASURED_CONFIGURATIONS = [c for c in CONFIGURATIONS if c["id"] == "cirq-routecqc-maponly-v1"]

# Display-only metadata. Never merge into the execution registry above.
CONFIGURATION_ANNOTATIONS = {
    f"bqskit-l{level}": {
        "numerical_approximation": True,
        "approximation_note": (
            "Numerical approximation in the stock BQSKit workflow. "
            "Strict QCEC acceptance is not guaranteed. "
            "The investigated ising_n10 output was not accepted within the worker budget. "
            "Individual check results, measurements, and scores are unchanged."
        ),
    }
    for level in (2, 3, 4)
}


def configuration_annotations() -> dict:
    """Return independent display notes without modifying execution settings."""
    return {identifier: dict(note) for identifier, note in CONFIGURATION_ANNOTATIONS.items()}


def configuration_for(identifier: str) -> dict:
    # Keep the previous adapter entry points usable by existing pipeline tests.
    identifier = {"qiskit": "qiskit-l2", "pytket": "pytket-peephole", "bqskit": "bqskit-l1"}.get(
        identifier, identifier
    )
    for configuration in CONFIGURATIONS:
        if configuration["id"] == identifier:
            return configuration
    raise ValueError(f"Unknown configuration: {identifier}")


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


def compile_once(original, compiler: str, target: str, seed: int, *, frozen_qasm=None):
    from qiskit import qasm2

    configuration = configuration_for(compiler)
    compiler = configuration["compiler"]
    n = original.num_qubits
    edges = edges_for(n, target)
    if compiler == "qiskit":
        from qiskit.transpiler import CouplingMap
        from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

        start = time.perf_counter_ns()
        pm = generate_preset_pass_manager(
            optimization_level=configuration["optimization_level"],
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
            GreedyPauliSimp,
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
        recipe = configuration["recipe"]
        optimisation = (
            [SynthesiseTket()] if recipe == "basic" else [FullPeepholeOptimise(allow_swaps=False)]
        )
        if recipe == "pauli":
            optimisation.insert(
                0,
                GreedyPauliSimp(
                    seed=seed,
                    thread_timeout=5,
                    trials=1,
                    only_reduce=True,
                ),
            )
        pipeline = SequencePass(
            [
                *optimisation,
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
    elif compiler == "bqskit":
        from bqskit import compile as bq_compile
        from bqskit.compiler import Compiler, MachineModel
        from bqskit.ext.qiskit import qiskit_to_bqskit
        from bqskit.ir.gates import CNOTGate, RZGate, SXGate, XGate
        from bqskit.ir.lang.qasm2 import OPENQASM2Language

        circuit = qiskit_to_bqskit(original)
        # Local runtime startup/shutdown is outside the compile timer.
        with Compiler(num_workers=1, num_blas_threads=1) as runtime:
            start = time.perf_counter_ns()
            model = MachineModel(
                n,
                coupling_graph=[(a, b) for a, b in edges if a < b],
                gate_set={RZGate(), SXGate(), XGate(), CNOTGate()},
            )
            compiled, initial, final = bq_compile(
                circuit,
                model=model,
                optimization_level=configuration["optimization_level"],
                max_synthesis_size=2,
                synthesis_epsilon=BQSKIT_EPSILON,
                seed=seed,
                with_mapping=True,
                compiler=runtime,
            )
            elapsed = (time.perf_counter_ns() - start) / 1e6
        native = qasm2.loads(
            OPENQASM2Language().encode(compiled),
            custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS,
        )
        initial, final = list(initial), list(final)
    elif compiler == "qmap":
        from qmap_adapter import NativeTarget, compile_native

        return compile_native(original, NativeTarget(n, tuple(edges), tuple(sorted(BASIS))))
    elif compiler == "cirq":
        from cirq_adapter import compile_native
        from qmap_adapter import NativeTarget

        if original.num_clbits or original.ancillas:
            raise ValueError("Classical or ancilla input")
        # Programmatic circuit API uses QASM plus a separate scalar. The worker
        # always supplies the original frozen bytes, never a Qiskit re-export.
        data = frozen_qasm if frozen_qasm is not None else qasm2.dumps(original).encode()
        order = tuple((r.name, i) for r in original.qregs for i in range(r.size))
        return compile_native(
            data,
            order,
            NativeTarget(n, tuple(edges), tuple(sorted(BASIS))),
            input_phase=float(original.global_phase),
        )
    else:
        raise ValueError(compiler)
    return native, elapsed, initial, final


def worker(
    case: dict, compiler: str, target: str, seed: int, *, artifact_root: Path | None = None
) -> dict:
    from qiskit import qasm2

    configuration = configuration_for(compiler)
    if artifact_root is None and (ROOT / "data/results.json").exists():
        raise RuntimeError("Existing measurements must not be overwritten")
    output_dir = artifact_root if artifact_root is not None else ROOT / "data" / "outputs"
    if any(path.is_symlink() for path in [output_dir, *output_dir.parents]):
        raise ValueError("Symlink artifact directory")
    if artifact_root is None and not output_dir.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Escaping artifact directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    frozen = (ROOT / case["path"]).read_bytes()
    if hashlib.sha256(frozen).hexdigest() != case["sha256"]:
        raise ValueError("Frozen input hash mismatch")
    original = qasm2.loads(frozen.decode())
    timings = []
    trials = []
    for _ in range(REPEATS):
        native, elapsed, initial, final = compile_once(
            original, compiler, target, seed, frozen_qasm=frozen
        )
        timings.append(elapsed)
        trials.append(
            {
                "metrics": metrics(native, edges_for(case["qubits"], target)),
                "validation": check_equivalence(original, native, initial, final),
                "initial_map": initial,
                "final_map": final,
                "global_phase": float(native.global_phase),
                "qasm": qasm2.dumps(native),
            }
        )
    artifacts = []
    for i, trial in enumerate(trials):
        filename = f"{case['id']}-{target}-{configuration['id']}-s{seed}-r{i}.qasm"
        path = output_dir / filename
        with path.open("x") as stream:
            stream.write(trial.pop("qasm") + "\n")
        trial["artifact"] = (
            str(path.resolve()) if artifact_root is not None else str(path.relative_to(ROOT))
        )
        trial["artifact_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        artifacts.append(trial)
    valid = all(t["validation"]["accepted"] for t in trials)
    return {
        "case_id": case["id"],
        "family": case["family"],
        "qubits": case["qubits"],
        "compiler": configuration["compiler"],
        "configuration_id": configuration["id"],
        "target": target,
        "seed": seed,
        "seed_supported": configuration["seed_supported"],
        "status": "passed" if valid else "verification_failed",
        "compile_ms": statistics.median(timings),
        "timing_samples_ms": timings,
        "worker_timeout_seconds": WORKER_TIMEOUT_SECONDS,
        "metrics": {
            key: statistics.median(t["metrics"][key] for t in trials)
            for key in ["two_qubit_count", "two_qubit_depth", "total_depth", "one_qubit_count"]
        },
        "trials": artifacts,
    }


def execute_job(
    case: dict,
    configuration: str,
    target: str,
    seed: int,
    env: dict,
    *,
    artifact_root: Path | None = None,
) -> dict:
    spec_path = ROOT / "campaign.json"
    if artifact_root is None and spec_path.exists():
        spec = json.loads(spec_path.read_text())
        if spec.get("spec_format_version") == 3:
            from retention_campaign import execute_job as execute_retained

            return execute_retained(ROOT, case, configuration, target, seed, env)
    command = [
        sys.executable,
        str(ROOT / "atlas.py"),
        "worker",
        case["id"],
        configuration,
        target,
        str(seed),
    ]
    if artifact_root is not None:
        command.extend(["--artifact-root", str(artifact_root.resolve())])
    try:
        with subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        ) as execution:
            try:
                stdout, stderr = execution.communicate(timeout=WORKER_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(execution.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                execution.communicate()
                raise
            except BaseException:
                try:
                    os.killpg(execution.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                execution.communicate()
                raise
            if execution.returncode:
                raise RuntimeError(stderr[-4000:])
            result = json.loads(stdout)
            expected = {
                "case_id": case["id"],
                "configuration_id": configuration,
                "target": target,
                "seed": seed,
                "worker_timeout_seconds": WORKER_TIMEOUT_SECONDS,
            }
            if not isinstance(result, dict) or any(
                key not in result or result[key] != value for key, value in expected.items()
            ):
                raise RuntimeError("Worker identity or budget mismatch")
    except subprocess.TimeoutExpired:
        result = {
            "status": "timeout",
            "error": f"{WORKER_TIMEOUT_SECONDS} s worker budget exceeded",
        }
    except (RuntimeError, json.JSONDecodeError) as error:
        result = {"status": "error", "error": str(error)}
    spec = configuration_for(configuration)
    result.update(
        case_id=case["id"],
        family=case["family"],
        qubits=case["qubits"],
        compiler=spec["compiler"],
        configuration_id=configuration,
        seed_supported=spec["seed_supported"],
        target=target,
        seed=seed,
        worker_timeout_seconds=WORKER_TIMEOUT_SECONDS,
    )
    return result


def read_completed_results(log: Path, jobs: list) -> list[dict]:
    results = []
    for line in log.read_text().splitlines():
        entry = json.loads(line)
        index = len(results)
        if index >= len(jobs) or entry["scheduled"] != len(jobs) or entry["completed"] != index + 1:
            raise ValueError("Resume log is not a contiguous prefix of this schedule")
        case, configuration, target, seed = jobs[index]
        result = entry["result"]
        expected = (case["id"], configuration, target, seed)
        actual = tuple(result[k] for k in ("case_id", "configuration_id", "target", "seed"))
        if actual != expected or result["compiler"] != configuration_for(configuration)["compiler"]:
            raise ValueError("Resume log does not match this schedule")
        for trial in result.get("trials", []):
            if not (ROOT / trial["artifact"]).is_file():
                raise ValueError("Resume artifact is missing")
        results.append(result)
    return results


def run_pilot(*, overwrite: bool = False, resume_log: Path | None = None) -> None:
    from campaign import finish, input_cases, validate_record, validate_workspace

    if overwrite or resume_log is not None:
        raise RuntimeError("New campaigns cannot overwrite or resume")
    if (ROOT / "data/results.json").exists():
        raise RuntimeError("Existing results are protected; use campaign --into a new directory")
    spec = validate_workspace(ROOT)
    with (ROOT / "RUN_STARTED").open("x") as stream:
        stream.write(datetime.now(UTC).isoformat() + "\n")
    if not hasattr(os, "sched_setaffinity"):
        raise RuntimeError("This pilot requires Linux CPU affinity")
    allowed = sorted(os.sched_getaffinity(0))
    selected = allowed[0]
    os.sched_setaffinity(0, {selected})
    cases = input_cases(ROOT)
    jobs = [
        (case, compiler, target, seed)
        for case in cases
        for compiler in [c["id"] for c in MEASURED_CONFIGURATIONS]
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
    resumed_entries = 0
    resume_hash = None
    with (ROOT / "data/run.jsonl").open("x") as log:
        for case, compiler, target, seed in jobs:
            result = execute_job(case, compiler, target, seed, env)
            validate_record(ROOT, result, case, compiler, target, seed)
            results.append(result)
            entry = json.dumps(
                {"completed": len(results), "scheduled": len(jobs), "result": result}
            )
            log.write(entry + "\n")
            log.flush()
            print(entry, flush=True)
    cpu = next(
        (
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name")
        ),
        "unknown",
    )
    document = {
        "schema_version": 2,
        "suite": MEASUREMENT_SUITE,
        "campaign_id": spec["campaign_id"],
        "source_commit": spec["source_commit"],
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
                for p in [
                    *SDK_PACKAGES.values(),
                    "pytket-qiskit",
                    "mqt.qcec",
                    "bqskitrs",
                    "mqt.core",
                ]
            },
            "distributions": {
                d.metadata["Name"]: d.version for d in importlib.metadata.distributions()
            },
            "exclusive_machine": False,
            "memory_limit_enforced": False,
        },
        "protocol": {
            "seeds": SEEDS,
            "timing_repeats": REPEATS,
            "compilers": [c["compiler"] for c in MEASURED_CONFIGURATIONS],
            "sdk_packages": {
                c["compiler"]: SDK_PACKAGES[c["compiler"]] for c in MEASURED_CONFIGURATIONS
            },
            "cirq_pipeline": configuration_for("cirq-routecqc-maponly-v1")["recipe"],
            "cirq_seed_note": (
                "No mapper seed API; slots 7/19/43 are independent repetitions, not RNG seeds."
            ),
            "configurations": MEASURED_CONFIGURATIONS,
            "reference_configuration": REFERENCE_CONFIGURATION,
            "worker_timeout_seconds": WORKER_TIMEOUT_SECONDS,
            "resumed_entries": resumed_entries,
            "resume_log_sha256": resume_hash,
            "basis": sorted(BASIS),
            "physical_qubits": "equal to input width",
            "timer": "pipeline construction + compilation; excludes parse, export, validation",
            "cold_worker": True,
            "input_track": "Qiskit level-0 lowered common OpenQASM 2; not high-level track",
            "pytket_pipeline": {
                "basic": ["SynthesiseTket"],
                "peephole": ["FullPeepholeOptimise(allow_swaps=False)"],
                "pauli": [
                    "GreedyPauliSimp(seed=slot, thread_timeout=5, trials=1, only_reduce=True)",
                    "FullPeepholeOptimise(allow_swaps=False)",
                ],
                "shared_suffix": [
                    "DefaultMappingPass(GraphPlacement)",
                    "SynthesiseTket",
                    "AutoRebase(rz,sx,x,cx,allow_swaps=False)",
                ],
            },
            "qiskit_pipeline": "preset levels 0/1/2/3, approximation_degree=1.0",
            "bqskit_pipeline": {
                "optimization_levels": [1, 2, 3, 4],
                "max_synthesis_size": 2,
                "synthesis_epsilon": BQSKIT_EPSILON,
                "num_workers": 1,
                "num_blas_threads": 1,
                "with_mapping": True,
                "error_threshold": None,
                "runtime_timing": (
                    "local runtime startup/shutdown excluded; new runtime per repetition"
                ),
            },
            "validation": "QCEC decision diagrams, no simulation/ZX, 20 s verification timeout",
        },
        "cases": cases,
        "results": results,
    }
    finish(ROOT, document)


def _terminate(_signum, _frame):
    raise KeyboardInterrupt("Campaign terminated; incomplete workspace retained")


def main() -> None:
    signal.signal(signal.SIGTERM, _terminate)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["campaign", "run", "worker", "retention-campaign", "retention-run"]
    )
    parser.add_argument("args", nargs="*")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--resume-log", type=Path)
    parser.add_argument("--into", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--inherit-file-map", help="Explicit repository-relative sealed source FileMap"
    )
    parser.add_argument(
        "--artifact-root", type=Path, help="Diagnostic outputs only, never campaign data"
    )
    options = parser.parse_args()
    if options.action not in {"campaign", "retention-campaign"} and (
        options.into is not None or options.prepare_only or options.inherit_file_map is not None
    ):
        parser.error("--into, --prepare-only and --inherit-file-map require campaign")
    if options.action.startswith("retention-") and (
        options.overwrite or options.resume_log is not None or options.inherit_file_map is not None
    ):
        parser.error("Standalone campaigns cannot overwrite, resume or inherit a FileMap")
    if options.action != "worker" and (options.args or options.artifact_root is not None):
        parser.error("Worker arguments and --artifact-root require worker")
    if options.action == "campaign" and (options.overwrite or options.resume_log is not None):
        parser.error("Campaigns cannot overwrite or resume")
    if options.action == "retention-campaign":
        from retention_campaign import create

        if options.into is None:
            parser.error("retention-campaign requires --into")
        print(create(options.into, prepare_only=options.prepare_only))
    elif options.action == "retention-run":
        from retention_campaign import run

        run(ROOT)
    elif options.action == "campaign":
        from campaign import create

        if options.into is None:
            parser.error("campaign requires --into")
        print(
            create(
                options.into,
                prepare_only=options.prepare_only,
                inherited_file_map=options.inherit_file_map,
            )
        )
    elif options.action == "run":
        run_pilot(overwrite=options.overwrite, resume_log=options.resume_log)
    else:
        case_id, compiler, target, seed = options.args
        manifest = json.loads((ROOT / "data" / "manifest.json").read_text())
        case = next(c for c in manifest if c["id"] == case_id)
        from campaign import validate_worker
        from qmap_adapter import CompilationError

        if options.artifact_root is None:
            validate_worker(ROOT, case, compiler, target, int(seed))
        else:
            destination = options.artifact_root.resolve()
            protected = [ROOT / "data", ROOT / "releases", ROOT.with_name("transpiler-atlas")]
            if any(destination.is_relative_to(path.resolve()) for path in protected):
                raise ValueError("Protected diagnostic output location")
        try:
            result = worker(case, compiler, target, int(seed), artifact_root=options.artifact_root)
        except CompilationError as error:
            config = configuration_for(compiler)
            result = {
                "status": "error",
                "error_kind": error.reason,
                "error": str(error),
                "case_id": case_id,
                "family": case["family"],
                "qubits": case["qubits"],
                "compiler": config["compiler"],
                "configuration_id": config["id"],
                "seed_supported": config["seed_supported"],
                "target": target,
                "seed": int(seed),
                "worker_timeout_seconds": WORKER_TIMEOUT_SECONDS,
            }
        print(json.dumps(result))


if __name__ == "__main__":
    main()
