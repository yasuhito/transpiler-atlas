"""Cirq routing-only recipe. SDK objects and export fallbacks stay at this boundary."""

import math
import time
import warnings

from qmap_adapter import CompilationError, NativeTarget

CONFIGURATION_ID = "cirq-routecqc-maponly-v1"


def recipe_metadata():
    """Return a fresh descriptor without importing any compiler SDK."""
    return {
        "cirq_core_version": "1.7.0",
        "input": "frozen QASM2 bytes in declaration order",
        "initial_mapper": "LineInitialMapper",
        "router": "RouteCQC.route_circuit",
        "lookahead_radius": 8,
        "tag_inserted_swaps": True,
        "context_deep": False,
        "tags_to_ignore": [],
        "qasm_version": "2.0",
        "qasm_precision": 17,
        "lowering": ["BasisTranslator"],
        "optimizers": [],
        "seed_supported": False,
    }


def compile_native(qasm_bytes: bytes, order, target: NativeTarget, *, input_phase=0.0):
    """Route original QASM bytes; scalar supplied separately because QASM2 omits it."""
    try:
        return _compile_native(qasm_bytes, order, target, input_phase)
    except CompilationError:
        raise
    except Exception as error:
        raise CompilationError("cirq_native_error", str(error)) from error


def _compile_native(qasm_bytes, order, target, input_phase):
    import importlib.metadata

    import cirq
    import networkx as nx
    from cirq.contrib.qasm_import import circuit_from_qasm
    from qiskit import qasm2
    from qiskit.circuit.equivalence_library import SessionEquivalenceLibrary
    from qiskit.transpiler import PassManager
    from qiskit.transpiler.passes import BasisTranslator

    if importlib.metadata.version("cirq-core") != "1.7.0":
        raise CompilationError("cirq_version_mismatch")
    n = target.width
    if n < 1 or target.basis != ("cx", "rz", "sx", "x") or len(order) != n:
        raise CompilationError("target_width_or_basis_mismatch")
    if not math.isfinite(float(input_phase)):
        raise CompilationError("cirq_global_phase_operation")
    named = [cirq.NamedQubit(f"{register}_{index}") for register, index in order]
    if len(set(named)) != n:
        raise CompilationError("cirq_incomplete_mapping")
    physical = tuple(cirq.LineQubit.range(n))
    parsed = circuit_from_qasm(qasm_bytes.decode("utf-8"))
    if not parsed.all_qubits().issubset(set(named)):
        raise CompilationError("cirq_incomplete_mapping")
    circuit = parsed.transform_qubits(dict(zip(named, physical, strict=True)))
    allowed = (
        cirq.HPowGate,
        cirq.XPowGate,
        cirq.YPowGate,
        cirq.ZPowGate,
        cirq.CXPowGate,
        cirq.IdentityGate,
    )
    if any(not isinstance(op.gate, allowed) for op in circuit.all_operations()):
        raise CompilationError("cirq_unsupported_operation")
    circuit.append(cirq.I(q) for q in physical if q not in circuit.all_qubits())
    start = time.perf_counter_ns()
    graph = nx.Graph()
    graph.add_nodes_from(physical)
    graph.add_edges_from((physical[a], physical[b]) for a, b in target.directed_edges)
    mapper = cirq.LineInitialMapper(graph)
    router = cirq.RouteCQC(graph)
    translator = PassManager([BasisTranslator(SessionEquivalenceLibrary, list(target.basis))])
    routed, initial_map, permutation = router.route_circuit(
        circuit,
        initial_mapper=mapper,
        lookahead_radius=8,
        tag_inserted_swaps=True,
        context=cirq.TransformerContext(deep=False, tags_to_ignore=()),
    )
    if any(not isinstance(op.gate, (*allowed, cirq.SwapPowGate)) for op in routed.all_operations()):
        raise CompilationError("cirq_unsupported_operation")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        text = str(
            cirq.QasmOutput(routed.all_operations(), qubits=physical, precision=17, version="2.0")
        )
    native = qasm2.loads(text, custom_instructions=qasm2.LEGACY_CUSTOM_INSTRUCTIONS)
    native.global_phase += float(input_phase)
    native = translator.run(native)
    elapsed_ms = (time.perf_counter_ns() - start) / 1e6
    try:
        initial = [physical.index(initial_map[q]) for q in physical]
        final = [physical.index(permutation[initial_map[q]]) for q in physical]
    except (KeyError, ValueError) as error:
        raise CompilationError("cirq_incomplete_mapping") from error
    if sorted(initial) != list(range(n)) or sorted(final) != list(range(n)):
        raise CompilationError("incomplete_or_nonbijective_permutation")
    if native.num_qubits != n:
        raise CompilationError("width_changed")
    if native.ancillas or native.num_clbits:
        raise CompilationError("added_workspace")
    # Common metrics also checks arity/coupling. Reject unexpected lowering here.
    if any(item.operation.name not in target.basis for item in native.data):
        raise CompilationError("cirq_unsupported_operation")
    return native, elapsed_ms, initial, final
