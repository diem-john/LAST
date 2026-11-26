"""Parameterized QAOA sampling circuit implemented with NVIDIA CUDA-Q.

The circuit implements the Ising cost Hamiltonian obtained from the QUBO
conversion helper. CUDA-Q is imported lazily so classical tests and tools can
use the package without installing CUDA-Q.
"""


def build_qaoa_sampling_kernel():
    try:
        import cudaq
    except ImportError as exc:
        raise ImportError(
            "CUDA-Q is required to execute the QAOA circuit. "
            "Install a CUDA-Q build compatible with your CUDA/GPU environment."
        ) from exc

    @cudaq.kernel
    def qaoa_kernel(
        qubit_count: int,
        gamma_values: list[float],
        beta_values: list[float],
        ising_linear: list[float],
        ising_quadratic_flat: list[float],
    ):
        qubits = cudaq.qvector(qubit_count)

        # Uniform superposition over all binary tie configurations.
        for i in range(qubit_count):
            h(qubits[i])

        # Alternating cost and transverse-field mixer layers.
        for layer in range(len(gamma_values)):
            # exp(-i * gamma * h_i * Z_i) = RZ(2 * gamma * h_i)
            for i in range(qubit_count):
                rz(2.0 * gamma_values[layer] * ising_linear[i], qubits[i])

            # exp(-i * gamma * J_ij * Z_i Z_j) via CNOT-RZ-CNOT.
            for i in range(qubit_count):
                for j in range(i + 1, qubit_count):
                    coupling = ising_quadratic_flat[i * qubit_count + j]
                    if coupling != 0.0:
                        x.ctrl(qubits[i], qubits[j])
                        rz(2.0 * gamma_values[layer] * coupling, qubits[j])
                        x.ctrl(qubits[i], qubits[j])

            # exp(-i * beta * X_i) = RX(2 * beta)
            for i in range(qubit_count):
                rx(2.0 * beta_values[layer], qubits[i])

        # CUDA-Q global bitstrings follow qubit allocation order: q[0] is leftmost.
        mz(qubits)

    return qaoa_kernel
