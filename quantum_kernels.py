from typing import Optional
from collections.abc import Callable, Iterable
from itertools import combinations, chain

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit import ParameterVector
from qiskit.circuit.library import PauliFeatureMap
from qiskit_machine_learning.kernels import FidelityStatevectorKernel


class VectorizeKernel:
    def __init__(self, kernel: Callable[[np.ndarray, np.ndarray], float]) -> None:
        '''
        Vectorizes a kernel function to return a kernel matrix.

        Parameters
        ----------
        kernel : Callable[[np.ndarray, np.ndarray], float]
            The unvectorized kernel function.
        '''

        self.kernel = kernel

    def __call__(self, X: np.ndarray, Y: Optional[np.ndarray] = None) -> np.ndarray:
        '''
        Computes the kernel matrix. Returns a numpy array K of shape (X.shape[0], Y.shape[0])
        where K[i, j] is given by kernel(X[i], Y[j]).

        Parameters
        ----------
        X : np.ndarray
            An array of shape (n_samples, n_features) of input data.
        Y : np.ndarray | None, optional
            An array of shape (n_samples, n_features) of input data. If None,

        Returns
        -------
        np.ndarray
            The computed kernel matrix of X and Y.
        '''

        if Y is None:
            Y = X

        # I compared this to fancier vectorization using np.vectorize, np.fromfunction, or np.frompyfunc,
        # but simple nested loops are faster in Python 3.11.
        computed_kernel = np.empty((X.shape[0], Y.shape[0]))
        for i, x in enumerate(X):
            for j, y in enumerate(Y):
                computed_kernel[i, j] = self.kernel(x, y)

        return computed_kernel


class Kernel:
    def __init__(
        self,
        feature_map: QuantumCircuit,
        fm_name: Optional[str] = None,
        preprocess_func: Optional[Callable[[np.ndarray], np.ndarray]] = None,
    ) -> None:
        '''
        Given a feature map φ and input data x and y, the kernel computes the square norm
        of the overlap |<φ(x)|φ(y)>|^2 or |φ(x)> and |φ(y)>.

        Parameters
        ----------
        feature_map : qiskit.QuantumCircuit
            The parameterized quantum circuit defining the feature map φ.
        fm_name : str | None, optional
            The name of the feature map. Default is None.
        preprocess_func : Callable[[np.ndarray], np.ndarray] | None, optional
            A proprocessing function f applied to the data before passing to the feature map.
            If provided, overlaps are computed between |φ(f(x))> and |φ(f(y))>. Default is None.
        '''

        self.fm_name = fm_name
        self.feature_map = feature_map
        self.kernel = FidelityStatevectorKernel(feature_map=self.feature_map)
        self.preprocess_func = preprocess_func

    def __call__(self, x: np.ndarray, y: Optional[np.ndarray] = None) -> np.ndarray:
        '''
        Run the kernel to compute the overlaps of all points in x against all points in y.

        Parameters
        ----------
        x : np.ndarray
            The x data on which to apply the kernel.
        y : np.ndarray | None, optional
            The y data on which to apply the kernel. If None, y is set equal to x.
            Default is None.

        Returns
        -------
        np.ndarray
            The 2D kernel matrix.
        '''

        if self.preprocess_func is not None:
            x = self.preprocess_func(x)
        ret = self.kernel.evaluate(x_vec=x, y_vec=y)
        return ret

    def __str__(self) -> str:
        str = f'{self.__class__.__name__}'
        if self.fm_name is not None:
            str += f'(feature_map={self.fm_name})'
        return str

    def __repr__(self) -> str:
        return self.__str__()


def get_entanglement_pattern(num_qubits: int, entanglement: str, rep: int = 0) -> Iterable[tuple[int, int]]:
    '''
    Build the entanglement pattern. Descriptions of entanglement patterns are provided
    [here](https://docs.quantum.ibm.com/api/qiskit/qiskit.circuit.library.TwoLocal).

    Parameters
    ----------
    num_qubits : int
        The number of qubits for which to create the entanglement pattern.
    entanglement : str
        The entanglement pattern to return. One of 'full', 'linear', 'reverse_linear',
        'pairwise', 'circular', or 'sca'.
    rep : int, optional
        The repetition index for the entanglement pattern. Only used when
        `entanglement = 'sca'`. Default is 0.

    Returns
    -------
    Iterable[tuple[int, int]]
        The entanglement pattern.
    '''

    match entanglement:
        case 'full':
            pattern = combinations(range(num_qubits), 2)

        case 'linear':
            pattern = ((i, i + 1) for i in range(num_qubits - 1))

        case 'reverse_linear':
            pattern = ((i, i - 1) for i in range(num_qubits - 1, 0, -1))

        case 'pairwise':
            even_pattern = ((i, i + 1) for i in range(0, num_qubits - 1, 2))
            odd_pattern = ((i, i + 1) for i in range(1, num_qubits - 1, 2))
            pattern = chain(even_pattern, odd_pattern)

        case 'circular':
            pattern = chain([(num_qubits - 1, 0)], get_entanglement_pattern(num_qubits, 'linear'))

        case 'sca':
            circ_pattern = list(get_entanglement_pattern(num_qubits, 'circular'))
            pattern = (circ_pattern[(i - rep) % num_qubits] for i in range(num_qubits))
            if rep % 2 == 1:
                pattern = ((j, i) for i, j in pattern)

        case _:
            raise ValueError(f'Unknown entanglement pattern {entanglement}')

    return pattern


def pauli_feature_map(
    num_features: int, reps: int = 1, paulis: list[str] = ['Z', 'ZZ'], entanglement: str = 'linear'
) -> PauliFeatureMap:
    '''
    The Pauli feature map.

    Parameters
    ----------
    num_features : int
        Number of features in the input vector.
    reps : int, optional
        The number of repetitions of the feature map to add to the quantum circuit. Default is 1.
    paulis : list[str], optional
        The Pauli operators to use in the feature map. Default is ['Z', 'ZZ'].
    entanglement : str, optional
        One of 'full', 'linear', 'reverse_linear', 'pairwise', 'circular', or 'sca'. Default is 'linear'.
        See `get_entanglement_pattern`.

    Returns
    -------
    qiskit.circuit.library.PauliFeatureMap
        The quantum circuit defining the feature map.

    References
    ----------
    [1] Vojtech Havlicek, Antonio D. Corcoles, Kristan Temme, Aram W. Harrow, Abhinav Kandala,
        Jerry M. Chow, and Jay M. Gambetta. Supervised learning with quantum- enhanced feature spaces.
        Nature, 567(7747):209-212, Mar 2019.
    '''

    feature_map = PauliFeatureMap(num_features, reps=reps, paulis=paulis, entanglement=entanglement)
    return feature_map


def z_feature_map(num_features: int, reps: int = 1) -> PauliFeatureMap:
    '''
    The Z feature map.

    Parameters
    ----------
    num_features : int
        Number of features in the input vector.
    reps : int, optional
        The number of repetitions of the feature map to add to the quantum circuit. Default is 1.

    Returns
    -------
    qiskit.circuit.library.PauliFeatureMap
        The quantum circuit defining the feature map.
    '''

    return pauli_feature_map(num_features, reps=reps, paulis=['Z'])


def zz_feature_map(num_features: int, reps: int = 1, entanglement: str = 'linear') -> PauliFeatureMap:
    '''
    The ZZ feature map.

    Parameters
    ----------
    num_features : int
        Number of features in the input vector.
    reps : int, optional
        The number of repetitions of the feature map to add to the quantum circuit. Default is 1.
    entanglement : str, optional
        One of 'full', 'linear', 'reverse_linear', 'pairwise', 'circular', or 'sca'.  Default is 'linear'.
        See `get_entanglement_pattern`.

    Returns
    -------
    qiskit.circuit.library.PauliFeatureMap
        The quantum circuit defining the feature map.
    '''

    return pauli_feature_map(num_features, reps=reps, paulis=['Z', 'ZZ'], entanglement=entanglement)


def iqp_feature_map(num_features: int, reps: int = 1, entanglement: str = 'linear') -> QuantumCircuit:
    '''
    The instantaneous quantum polynomial feature map. Implements an IQP circuit embedding as in
    the Pennylane class in [3].

    Definition (Instantaneous quantum poylnomial circuit):
    An instantaneous quantum poylnomial (IQP) circuit on n qubit lines is a quantum circuit
    with the following structure: each gate in the circuit is diagonal in the X basis {|0⟩ ± |1⟩},
    the input state is |0⟩ |0⟩ . . . |0⟩ and the output is the result of a computational basis
    measurement on a specified set of output lines.

    Parameters
    ----------
    num_features : int
        Number of features in the input vector.
    reps : int, optional
        The number of repetitions of the feature map to add to the quantum circuit. Default is 1.
    entanglement : str, optional
        One of 'full', 'linear', 'reverse_linear', 'pairwise', 'circular', or 'sca'. Default is 'linear'.
        See `get_entanglement_pattern`.

    Returns
    -------
    qiskit.QuantumCircuit
        The quantum circuit defining the feature map.

    References
    ----------
    [2] Michael J. Bremner, Richard Jozsa, and Dan J. Shepherd. "Classical simulation of commuting
        quantum computations implies collapse of the polynomial hierarchy". Proceedings of the Royal
        Society A: Mathematical, Physical and Engineering Sciences, 467:459-472, 2010.
        https://arxiv.org/abs/1005.1407.
    [3] qml.iqpembedding. https://docs.pennylane.ai/en/stable/code/api/ pennylane.IQPEmbedding.html.
        Accessed Aug 15, 2024.
    '''

    feature_map = QuantumCircuit(num_features)
    params = ParameterVector('x', num_features)

    for rep in range(reps):
        feature_map.h(range(num_features))

        for i in range(num_features):
            feature_map.rz(2.0 * params[i], i)

        pattern = get_entanglement_pattern(num_features, entanglement, rep)
        for i, j in pattern:
            feature_map.rzz(2 * params[i] * params[j], i, j)

        feature_map.h(range(num_features))

    return feature_map


# def tensorial_feature_map(base_feature_map: QuantumCircuit, reps: int = 2) -> QuantumCircuit:
#     '''
#     https://arxiv.org/pdf/1804.00633

#     To map input data into vastly higher dimensional spaces we can apply a tensorial
#     feature map by preparing d copies of the state. If |ψ⟩ is the 'ket' vector produced
#     by a base feature map, this prepares |ψ⟩ → |ψ⟩^{⊗d}.

#     This feature map is not valuable for kernel methods as it merely raises the overlap
#     to the power d.
#     '''

#     num_qubits_base = base_feature_map.num_qubits
#     feature_map = QuantumCircuit(num_qubits_base * reps)
#     for i in range(reps):
#         feature_map.append(base_feature_map, range(num_qubits_base * i, num_qubits_base * (i + 1)), copy=True)
#     return feature_map


def polynomial_feature_map(num_features: int, qubits_per_feature: int = 2) -> QuantumCircuit:
    r'''
    The polynomial feature map as defined in [4] section II. C.

    The state density matrix is given by

    \frac{1}{2^N} \bigotimes_{k=1}^d \left( \bigotimes_{i=1}^n \left[ I + x_k X + \sqrt{1 - x_k^2} Z \right] \right)

    where n is the number of qubits per feature, d is the number of features, and N = n * d.
    For x_k \in [-1, 1], it can be implemented by applying an Ry rotation by angle
    sin^{-1}(x_k) to each qubit.

    Parameters
    ----------
    num_features : int
        Number of features in the input vector.
    qubits_per_feature : int, optional
        The number of qubits to associate with each feature. Default is 2.

    Returns
    -------
    qiskit.QuantumCircuit
        The quantum circuit defining the feature map.

    References
    ----------
    [4] K. Mitarai, M. Negoro, M. Kitagawa, and K. Fujii. "Quantum circuit learning".
        Phys. Rev. A, 98:032309, Sep 2018. https://arxiv.org/pdf/1803.00745.
    '''

    feature_map = QuantumCircuit(num_features * qubits_per_feature)
    params = ParameterVector('x', num_features)

    for k in range(num_features):
        for i in range(qubits_per_feature):
            feature_map.ry(params[k], k * qubits_per_feature + i)  # arcsin is offloaded to the preprocessing function

    return feature_map


def qaoa_inspired_feature_map(num_features: int, reps: int = 1, entanglement: str = 'linear') -> QuantumCircuit:
    '''
    The QAOA-inspired feature map.

    Parameters
    ----------
    num_features : int
        Number of features in the input vector.
    reps : int, optional
        The number of repetitions of the feature map to add to the quantum circuit. Default is 1.
    entanglement : str, optional
        One of 'full', 'linear', 'reverse_linear', 'pairwise', 'circular', or 'sca'. Default is 'linear'.
        See `get_entanglement_pattern`.

    Returns
    -------
    qiskit.QuantumCircuit
        The quantum circuit defining the feature map.

    References
    ----------
    [5] Edward Farhi, Jeffrey Goldstone, and Sam Gutmann. A quantum approximate optimization algorithm,
        2014. https://arxiv.org/abs/1411.4028.
    '''

    num_qubits = num_features // 2
    feature_map = QuantumCircuit(num_qubits)
    params = ParameterVector('x', num_qubits * 2)

    feature_map.h(range(num_qubits))

    for rep in range(reps):
        # Mixer Hamiltonian
        for i in range(num_qubits):
            feature_map.rx(2.0 * params[i], i)

        # Problem Hamiltonian
        for i in range(num_qubits):
            feature_map.rz(2.0 * params[num_qubits + i], i)

        pattern = list(get_entanglement_pattern(num_qubits, entanglement, rep))
        for i, j in pattern:
            feature_map.rzz(params[i] * params[j], i, j)
        for i, j in pattern:
            feature_map.rzz(params[num_qubits + i] * params[num_qubits + j], i, j)

    return feature_map


def random_feature_map(num_features: int, reps: int = 2, seed: Optional[int] = None) -> QuantumCircuit:
    '''
    The random feature map.  Encodes the input vector using random Hadamards, single qubit
    rotations, and CNOT gates.

    Parameters
    ----------
    num_features : int
        Number of features in the input vector.
    reps : int, optional
        The number of repetitions of the feature map to add to the quantum circuit. Default is 1.
    seed : int | None, optional
        A seed for reproducibility. Default is None.

    Returns
    -------
    qiskit.QuantumCircuit
        The quantum circuit defining the feature map.
    '''

    if seed is not None:
        np.random.seed(seed)

    feature_map = QuantumCircuit(num_features)
    params = reps * list(ParameterVector('x', num_features))
    np.random.shuffle(params)

    for _ in range(reps):
        for i in range(num_features):
            if np.random.random() < 0.5:
                feature_map.h(i)

        for i in range(num_features):
            gate = np.random.choice(['rx', 'ry', 'rz'])
            angle = params.pop()
            getattr(feature_map, gate)(2.0 * angle, i)

        for i in range(num_features):
            if np.random.random() < 0.5:
                qubits = (i, (i + 1) % num_features)
                index = np.random.choice((-1, 0))
                feature_map.cx(qubits[index], qubits[index + 1])

        feature_map.barrier()

    return feature_map


def data_reuploading_feature_map(num_features: int, reps: int = 1, entanglement: str = 'linear') -> QuantumCircuit:
    '''
    The data re-uploading feature map. Uploads the data multiple times to enrich the encoding.

    Parameters
    ----------
    num_features : int
        Number of features in the input vector.
    reps : int, optional
        The number of repetitions of the feature map to add to the quantum circuit. Default is 1.
    entanglement : str, optional
        One of 'full', 'linear', 'reverse_linear', 'pairwise', 'circular', or 'sca'. Default is 'linear'.
        See `get_entanglement_pattern`.

    Returns
    -------
    qiskit.QuantumCircuit
        The quantum circuit defining the feature map.

    References
    ----------
    [6] Adrian Perez-Salinas, Alba Cervera-Lierta, Elies Gil-Fuster, and Jose I. Latorre. "Data
        re-uploading for a universal quantum classifier". Quantum, 4:226, February 2020.
        https://arxiv.org/abs/1907.02085.

    '''

    feature_map = QuantumCircuit(num_features)
    params = ParameterVector('x', num_features * reps)

    feature_map.h(range(num_features))

    for d in range(reps):
        pattern = list(get_entanglement_pattern(num_features, entanglement, rep=d))
        for gate in ('rx', 'ry', 'rz'):
            for i in range(num_features):
                getattr(feature_map, gate)(params[i], i)
            for i, j in pattern:
                feature_map.cx(i, j)
            feature_map.barrier()

    return feature_map