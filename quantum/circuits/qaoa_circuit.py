"""Parameterized QAOA circuits implemented with NVIDIA CUDA-Q.

The state-preparation kernel is measurement-free for cudaq.observe.
The sampling kernel measures the prepared state for final shot-based evaluation.
CUDA-Q is imported lazily so classical tests can run without CUDA-Q installed.
"""


def _build_qaoa_kernel(measure: bool):
    try:
        import cudaq
    except ImportError as exc:
        raise ImportError(
            "CUDA-Q is required to execute the QAOA circuit. "
            "Install a CUDA-Q build compatible with your CUDA/GPU environment."
        ) from exc

    if measure:
        @cudaq.kernel
        def qaoa_kernel(
            qubit_count: int,
            gamma_values: list[float],
            beta_values: list[float],
            ising_linear: list[float],
            ising_quadratic_flat: list[float],
        ):
            qubits = cudaq.qvector(qubit_count)
            for i in range(qubit_count):
                h(qubits[i])
            for layer in range(len(gamma_values)):
                for i in range(qubit_count):
                    rz(2.0 * gamma_values[layer] * ising_linear[i], qubits[i])
                for i in range(qubit_count):
                    for j in range(i + 1, qubit_count):
                        coupling = ising_quadratic_flat[i * qubit_count + j]
                        if coupling != 0.0:
                            x.ctrl(qubits[i], qubits[j])
                            rz(2.0 * gamma_values[layer] * coupling, qubits[j])
                            x.ctrl(qubits[i], qubits[j])
                for i in range(qubit_count):
                    rx(2.0 * beta_values[layer], qubits[i])
            mz(qubits)
    else:
        @cudaq.kernel
        def qaoa_kernel(
            qubit_count: int,
            gamma_values: list[float],
            beta_values: list[float],
            ising_linear: list[float],
            ising_quadratic_flat: list[float],
        ):
            qubits = cudaq.qvector(qubit_count)
            for i in range(qubit_count):
                h(qubits[i])
            for layer in range(len(gamma_values)):
                for i in range(qubit_count):
                    rz(2.0 * gamma_values[layer] * ising_linear[i], qubits[i])
                for i in range(qubit_count):
                    for j in range(i + 1, qubit_count):
                        coupling = ising_quadratic_flat[i * qubit_count + j]
                        if coupling != 0.0:
                            x.ctrl(qubits[i], qubits[j])
                            rz(2.0 * gamma_values[layer] * coupling, qubits[j])
                            x.ctrl(qubits[i], qubits[j])
                for i in range(qubit_count):
                    rx(2.0 * beta_values[layer], qubits[i])

    return qaoa_kernel


def build_qaoa_sampling_kernel():
    """Build a QAOA kernel with computational-basis measurements."""
    return _build_qaoa_kernel(measure=True)


def build_qaoa_state_kernel():
    """Build the same QAOA ansatz without measurements for exact observe()."""
    return _build_qaoa_kernel(measure=False)
