"""
Embedding utility functions for vector operations.

Consolidates duplicate embedding parsing and similarity calculations
used across clustering and incremental assignment modules.
"""
import numpy as np
from typing import List


def parse_embedding_string(embedding_str: str) -> np.ndarray:
    """
    Parse embedding string from database to numpy array.

    Args:
        embedding_str: String representation of embedding like "[0.1, 0.2, ...]"

    Returns:
        NumPy array of floats (768-dimensional)

    Example:
        >>> embedding_str = "[0.1, 0.2, 0.3]"
        >>> arr = parse_embedding_string(embedding_str)
        >>> arr.shape
        (3,)
    """
    # Remove brackets and split by comma
    cleaned = embedding_str.strip('[]')
    values = [float(x) for x in cleaned.split(',')]
    return np.array(values)


def normalize_vector(vector: np.ndarray) -> np.ndarray:
    """
    Normalize a vector to unit length (L2 normalization).

    Args:
        vector: Input vector (any dimension)

    Returns:
        Normalized vector with L2 norm = 1

    Example:
        >>> v = np.array([3.0, 4.0])
        >>> normalized = normalize_vector(v)
        >>> np.linalg.norm(normalized)
        1.0
    """
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return vector / norm


def calculate_cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    Calculate cosine similarity between two vectors.

    Uses normalized dot product for efficient computation.
    Both vectors should be 768-dimensional embeddings.

    Args:
        vec1: First embedding vector
        vec2: Second embedding vector

    Returns:
        Cosine similarity score in range [-1, 1]
        (typically [0, 1] for sentence embeddings)

    Example:
        >>> v1 = np.array([1.0, 0.0, 0.0])
        >>> v2 = np.array([1.0, 0.0, 0.0])
        >>> calculate_cosine_similarity(v1, v2)
        1.0
    """
    # Normalize both vectors
    vec1_norm = normalize_vector(vec1)
    vec2_norm = normalize_vector(vec2)

    # Compute dot product of normalized vectors
    similarity = np.dot(vec1_norm, vec2_norm)

    # Ensure result is in valid range (handle floating point errors)
    return float(np.clip(similarity, -1.0, 1.0))


def batch_normalize_vectors(vectors: List[np.ndarray]) -> np.ndarray:
    """
    Normalize multiple vectors at once using vectorized operations.

    Args:
        vectors: List of vectors to normalize

    Returns:
        2D array where each row is a normalized vector

    Example:
        >>> vectors = [np.array([3, 4]), np.array([5, 12])]
        >>> normalized = batch_normalize_vectors(vectors)
        >>> normalized.shape
        (2, 2)
    """
    # Stack vectors into matrix
    matrix = np.vstack(vectors)

    # Compute norms for all vectors
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)

    # Avoid division by zero
    norms = np.where(norms == 0, 1, norms)

    # Normalize all at once
    return matrix / norms
