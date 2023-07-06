import math
from random import random, shuffle, sample, choice
import numpy as np
from collections import deque
from tiltmp.core.tumbletiles import Board
from tiltmp.core.gridutil import *


def uniform_random_grid(size, p):
    return np.where(np.random.rand(*size) < p, 1, 0)


class CellularRules:
    def __init__(self, birth_condition, death_condition):
        self._birth_condition = birth_condition
        self._death_condition = death_condition

    @staticmethod
    def _count_neighbors(grid, x, y):
        neighbors = 0
        for nx, ny in box_neighbors(x, y):
            if not is_legal_index(grid, (nx, ny)):
                neighbors += 1  # border counts as alive
            elif grid[nx, ny] == 1:
                neighbors += 1
        return neighbors

    def _get_next_state(self, current_state, living_neighbors):
        stay_alive = current_state == 1 and not self._death_condition(living_neighbors)
        born = current_state == 0 and self._birth_condition(living_neighbors)
        return 1 if stay_alive or born else 0

    def apply(self, grid):
        current_grid = np.copy(grid)
        for (x, y), alive in np.ndenumerate(current_grid):
            grid[x, y] = self._get_next_state(
                alive, self._count_neighbors(current_grid, x, y)
            )


class CellularAutomaton:
    def __init__(self, grid, rules):
        self._grid = grid
        self._rules = rules

    def step(self, generations):
        for _ in range(generations):
            self._rules.apply(self._grid)

    @property
    def grid(self):
        return self._grid


def connected_component(grid, x, y):
    symbol = grid[x, y]
    cc = {(x, y)}
    active = deque()
    active.append((x, y))
    while active:
        current = active.pop()
        for coord in direct_neighbors(*current):
            if not is_legal_index(grid, coord):
                continue
            if coord not in cc and grid[coord] == symbol:
                cc.add(coord)
                active.append(coord)
    return cc


# returns an array of the concrete positions for a randomized cave-like board
def generate_caves(
    size, cellular_rules=CellularRules(lambda ln: ln >= 5, lambda ln: ln < 4), p=0.45
):
    while True:
        ca = CellularAutomaton(uniform_random_grid(size, p), cellular_rules)
        ca.step(2)
        x, y = (0, 0)
        # try to find a large connected component of open space
        attempts = 0
        while ca.grid[x, y] != 0:
            x = np.random.randint(0, ca.grid.shape[0])
            y = np.random.randint(0, ca.grid.shape[1])
            attempts += 1
            if attempts > 10:
                return generate_caves(size, cellular_rules, p)

        cc = connected_component(ca.grid, x, y)
        if len(cc) > p * ca.grid.size:
            break

    # fill in small enclosures
    for coord, value in np.ndenumerate(ca.grid):
        if coord not in cc:
            ca.grid[coord] = 1

    return ca.grid


def count_neighbors(grid, x, y):
    neighbors = 0
    for nx, ny in box_neighbors(x, y):
        if not is_legal_index(grid, (nx, ny)):
            continue
        elif grid[nx, ny] == 1:
            neighbors += 1
    return neighbors


def generate_maze(size):
    import sys

    sys.setrecursionlimit(5000)
    x, y = np.random.randint(0, size[0]), np.random.randint(0, size[1])
    maze = np.zeros(shape=(size[0], size[1]), dtype=int)
    _generate_maze(maze, x, y)
    return np.where(maze == 0, 1, 0)

    # stack = deque()
    # stack.append((x, y))
    # while stack:
    #    x, y = stack.pop()
    #    neighbors = [n for n in direct_neighbors(x, y) if is_legal_index(maze, n)]
    #    shuffle(neighbors)
    #    for n in neighbors:
    #        if maze[n] == 0 and count_neighbors(maze, *n) < 3:
    #            maze[n] = 1
    #            stack.append(n)


# recursive backtracking algo
def _generate_maze(maze, x, y):
    neighbors = [n for n in direct_neighbors(x, y) if is_legal_index(maze, n)]
    shuffle(neighbors)
    for n in neighbors:
        if maze[n] == 0 and count_neighbors(maze, *n) < 3:
            maze[n] = 1
            _generate_maze(maze, *n)


def generate_maze_with_open_areas(size):
    maze = generate_maze(size)
    # Add open areas. The number depends on the size of the board
    size_factor = math.sqrt(np.prod(size))
    min_size = min(3, size[0] - 1, size[1] - 1)
    max_size = min(7, size[0] - 1, size[1] - 1)
    for _ in range(int(size_factor / 2)):
        size_x = np.random.randint(min_size, max_size)
        size_y = np.random.randint(min_size, max_size)
        position_x = np.random.randint(0, size[0] - size_x - 1)
        position_y = np.random.randint(0, size[1] - size_y - 1)
        maze[
            position_x : position_x + size_x, position_y : position_y + size_y
        ] = np.zeros(shape=(size_x, size_y), dtype=int)
    return maze


def random_maze_board(size):
    board = Board(size[0], size[1])
    concrete_positions = generate_maze_with_open_areas(size)
    for x, y in np.argwhere(concrete_positions == 1):
        board.add_concrete(x, y)
    return board


def random_maze_board_no_chambers(size):
    board = Board(size[0], size[1])
    concrete_positions = generate_maze(size)
    delete = sample(
        [(x, y) for x, y in np.argwhere(concrete_positions == 1)],
        k=int(size[0] * size[1] / 12),
    )

    for x, y in delete:
        for nx, ny in direct_neighbors(x, y):
            if not board.is_blocked(nx, ny):
                concrete_positions[x, y] = 0
                break

    for i in range(5):
        x, y = choice([(x, y) for x, y in np.argwhere(concrete_positions == 0)])
        cc = connected_component(concrete_positions, x, y)
        if len(cc) < 0.1 * size[0] * size[1]:
            if i == 4:
                raise Exception("Could not find a large connected component in maze")
            continue

    for coord, value in np.ndenumerate(concrete_positions):
        if coord not in cc:
            concrete_positions[coord] = 1

    for x, y in np.argwhere(concrete_positions == 1):
        board.add_concrete(x, y)

    return board


def random_cave_board(size):
    board = Board(size[0], size[1])
    concrete_positions = generate_caves(size)
    for x, y in np.argwhere(concrete_positions == 1):
        board.add_concrete(x, y)
    return board


def noise_array(dim, octaves):
    parameters = []
    start_amplitude = 10
    for n in range(octaves):
        parameters.append(
            {
                "offset": random() * 2 * math.pi,
                "frequency": 1.5**n,
                "amplitude": start_amplitude / float(n + 1),
            }
        )

    noise = np.zeros(dim, dtype=float)

    for (x, y), _ in np.ndenumerate(noise):
        for p in parameters:
            offset = math.sin(x / dim[0] * p["frequency"] * 2 * math.pi + p["offset"])
            noise[x, y] += (
                math.sin(y / dim[1] * p["frequency"] * 2 * math.pi + offset)
                * p["amplitude"]
            )
    return noise


def random_noise_grid(dim):
    noise = noise_array(dim, int(math.sqrt(dim[0] * dim[1]) / 4))
    concrete_positions = np.where(noise > 8, 1, 0)
    return concrete_positions
