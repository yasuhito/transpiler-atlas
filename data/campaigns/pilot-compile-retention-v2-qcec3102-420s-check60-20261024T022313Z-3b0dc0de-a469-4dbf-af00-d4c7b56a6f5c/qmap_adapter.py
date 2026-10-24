"""QMAP mapping-only recipe. Native SDK types stay inside this boundary."""

import time
from dataclasses import dataclass
from types import MappingProxyType

CONFIGURATION_ID = "qmap-sc-heuristic-maponly-v1"
SETTINGS = MappingProxyType(
    {
        "method": "heuristic",
        "heuristic": "gate_count_max_distance",
        "initial_layout": "dynamic",
        "layering": "individual_gates",
        "iterative_bidirectional_routing": False,
        "iterative_bidirectional_routing_passes": 0,
        "automatic_layer_splits": True,
        "automatic_layer_splits_node_limit": 5000,
        "early_termination": "none",
        "early_termination_limit": 0,
        "lookahead_heuristic": "gate_count_max_distance",
        "lookaheads": 15,
        "first_lookahead_factor": 0.75,
        "lookahead_factor": 0.5,
        "pre_mapping_optimizations": False,
        "post_mapping_optimizations": False,
        "add_measurements_to_mapped_circuit": False,
        "add_barriers_between_layers": False,
        "use_subsets": False,
        "subgraph": (),
        "encoding": "commander",
        "commander_grouping": "fixed3",
        "swap_reduction": "coupling_limit",
        "swap_limit": 0,
        "enable_limits": True,
        "timeout": 3600000,
        "verbose": False,
        "debug": False,
        "include_wcnf": False,
        "data_logging_path": "",
    }
)


@dataclass(frozen=True)
class NativeTarget:
    width: int
    directed_edges: tuple[tuple[int, int], ...]
    basis: tuple[str, ...]


class CompilationError(RuntimeError):
    def __init__(self, reason, message=None):
        self.reason = reason
        super().__init__(message or reason)


def recipe_metadata():
    return {
        key: list(value) if isinstance(value, tuple) else value for key, value in SETTINGS.items()
    }


def invert_permutation(permutation, n):
    pairs = list(permutation.items())
    if sorted(p for p, _ in pairs) != list(range(n)) or sorted(
        logical for _, logical in pairs
    ) != list(range(n)):
        raise CompilationError("incomplete_or_nonbijective_permutation")
    inverse = [0] * n
    for physical, logical in pairs:
        inverse[logical] = physical
    return inverse


def compile_native(original, target):
    try:
        return _compile_native(original, target)
    except CompilationError:
        raise
    except Exception as error:
        raise CompilationError("qmap_native_error", str(error)) from error


def _compile_native(original, target):
    from mqt.core import load
    from mqt.core.plugins.qiskit import mqt_to_qiskit
    from mqt.qmap import sc
    from qiskit.circuit.equivalence_library import SessionEquivalenceLibrary
    from qiskit.transpiler import PassManager
    from qiskit.transpiler.passes import BasisTranslator

    n = target.width
    if original.num_qubits != n or n < 1 or target.basis != ("cx", "rz", "sx", "x"):
        raise CompilationError("target_width_or_basis_mismatch")
    if original.num_clbits or original.ancillas:
        raise CompilationError("classical_or_ancilla_input")
    # QMAP 3.10 compacts idle inputs internally, without exporting that renaming.
    # Make the renaming explicit, keeping the full device width and every input wire.
    from qiskit import QuantumCircuit

    if any(item.operation.name not in {"h", "x", "rx", "ry", "rz", "cx"} for item in original.data):
        raise CompilationError("unsupported_input_basis")
    active = sorted({original.find_bit(q).index for item in original.data for q in item.qubits})
    order = active + [i for i in range(n) if i not in active]
    inverse_order = {logical: compact for compact, logical in enumerate(order)}
    prepared = QuantumCircuit(n)
    for item in original.data:
        prepared.append(
            item.operation, [inverse_order[original.find_bit(q).index] for q in item.qubits]
        )
    input_phase = float(original.global_phase)
    ir = load(prepared)
    enums = {
        "method": sc.Method,
        "heuristic": sc.Heuristic,
        "initial_layout": sc.InitialLayout,
        "layering": sc.Layering,
        "early_termination": sc.EarlyTermination,
        "lookahead_heuristic": sc.LookaheadHeuristic,
        "encoding": sc.Encoding,
        "commander_grouping": sc.CommanderGrouping,
        "swap_reduction": sc.SwapReduction,
    }
    start = time.perf_counter_ns()
    architecture = sc.Architecture(n, set(target.directed_edges))
    config = sc.Configuration()
    for key, value in SETTINGS.items():
        if key in enums:
            value = getattr(enums[key], value)
        elif key == "subgraph":
            value = set(value)
        setattr(config, key, value)
    translator = PassManager([BasisTranslator(SessionEquivalenceLibrary, list(target.basis))])
    mapped, result = sc.map_(ir, architecture, config)
    if result.timeout:
        raise CompilationError("qmap_internal_timeout")
    native = mqt_to_qiskit(mapped, set_layout=False)
    # map_ drops the input scalar phase in this pinned version. Map a phase-zero
    # circuit, then restore the saved scalar exactly once before basis lowering.
    native.global_phase = input_phase + mapped.global_phase
    native = translator.run(native)
    elapsed_ms = (time.perf_counter_ns() - start) / 1e6
    actual = {}
    for key in SETTINGS:
        value = getattr(config, key)
        actual[key] = value.name if key in enums else sorted(value) if key == "subgraph" else value
    if actual != recipe_metadata():
        raise CompilationError("configuration_readback_mismatch")
    if any(width != n for width in [ir.num_qubits, mapped.num_qubits, native.num_qubits]):
        raise CompilationError("width_changed")
    if mapped.num_ancilla_qubits or native.ancillas or native.num_clbits:
        raise CompilationError("added_workspace")
    raw_initial = dict(mapped.initial_layout.items())
    invert_permutation(raw_initial, n)
    raw_final = dict(mapped.output_permutation.items())
    if len(raw_final) != n:
        # Never fill missing entries with identity. Track idle states through actual
        # routing SWAPs and cross-check every exported active output permutation.
        from mqt.core.ir.operations import OpType

        tracked = dict(raw_initial)
        for operation in mapped:
            if operation.type_ == OpType.swap:
                a, b = operation.targets
                tracked[a], tracked[b] = tracked[b], tracked[a]
        if sorted(raw_final.values()) != list(range(len(active))):
            raise CompilationError("missing_active_output_permutation")
        if any(tracked.get(p) != logical for p, logical in raw_final.items()):
            raise CompilationError("routing_permutation_mismatch")
        raw_final = tracked
    initial = invert_permutation(
        {physical: order[logical] for physical, logical in raw_initial.items()}, n
    )
    final = invert_permutation(
        {physical: order[logical] for physical, logical in raw_final.items()}, n
    )
    return native, elapsed_ms, initial, final
