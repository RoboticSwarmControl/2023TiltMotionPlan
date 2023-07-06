import cProfile
from time import time


def direct_neighbors(x, y):
    for dx, dy in (0, -1), (0, 1), (-1, 0), (1, 0):
        yield x + dx, y + dy


def box_neighbors(x, y):
    for dx, dy in (
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    ):
        yield x + dx, y + dy


def is_legal_index(array, index):
    return (0 <= index[0] < array.shape[0]) and (0 <= index[1] < array.shape[1])
