import json
import os
import time
from copy import copy
from typing import Iterable, Set, Dict
from queue import PriorityQueue

from tiltmp.core.tumbletiles import *


def breadth_first_reachable(start, neighbors, is_valid_neighbor=lambda n: True):
    return breadth_first_distance(
        start, neighbors, is_valid_neighbor=is_valid_neighbor
    ).keys()


def breadth_first_distance(start, neighbors, is_valid_neighbor=lambda n: True):
    distance = {t: 0 for t in start}
    active = deque(distance.keys())
    while active:
        current = active.popleft()
        for xy in neighbors(current):
            if xy not in distance and is_valid_neighbor(xy):
                distance[xy] = distance[current] + 1
                active.append(xy)
    return distance


def breadth_first_path_exists(
    start, goal_condition, neighbors, is_valid_neighbor=lambda n: True
):
    distance = {t: 0 for t in start}
    active = deque(distance.keys())
    while active:
        current = active.popleft()
        for xy in neighbors(current):
            if xy not in distance and is_valid_neighbor(xy):
                if goal_condition(xy):
                    return distance
                distance[xy] = distance[current] + 1
                active.append(xy)
    return False


def reachable_set(board, poly):
    position, rel_coord = poly.get_shape()
    reachable = {position}
    active = deque([position])
    while active:
        current = active.popleft()
        for xy in direct_neighbors(*current):
            if xy not in reachable and board.fits(xy, rel_coord):
                reachable.add(xy)
                active.append(xy)
    return reachable


def compute_distances(board, target_shape):
    distance = {(t.x, t.y): 0 for t in target_shape.get_tiles()}
    active = deque(distance.keys())
    while active:
        current = active.popleft()
        for xy in direct_neighbors(*current):
            if not board.is_blocked(*xy) and xy not in distance:
                distance[xy] = distance[current] + 1
                active.append(xy)
    result = np.full((board.rows, board.cols), float("inf"), dtype=float)
    for coord, dist in distance.items():
        result[coord] = float(dist)
    return result


def compute_distance_within_set(board, target_shape, s):
    distance = {(t.x, t.y): 0 for t in target_shape.get_tiles()}
    active = deque(distance.keys())
    while active:
        current = active.popleft()
        for xy in direct_neighbors(*current):
            if not board.is_blocked(*xy) and xy not in distance and xy in s:
                distance[xy] = distance[current] + 1
                active.append(xy)
    result = np.full((board.rows, board.cols), float("inf"), dtype=float)
    for coord, dist in distance.items():
        result[coord] = float(dist)
    return result


class PathsTree:
    def __init__(self, paths: dict):
        self._paths = paths

    def __contains__(self, item):
        return item in self._paths

    def get_path(self, position):
        if position not in self._paths:
            return None
        current = position
        path = []
        while current is not None:
            path.append(current)
            current = self._paths[current]
        return tuple(reversed(path))

    def get_moves(self, position: tuple):
        path = self.get_path(position)
        if path is None:
            return None
        if len(path) == 1:
            return []
        differences = [(x2 - x1, y2 - y1) for (x1, y1), (x2, y2) in zip(path, path[1:])]
        return [Direction.from_vector(d) for d in differences]

    @staticmethod
    def compute_shortest_paths_tree(board: Board, polyomino: Polyomino):
        position, rel_coord = polyomino.get_shape()
        # maps position to previous position on the shortest path
        paths = {position: None}
        active = deque([position])
        while active:
            current = active.popleft()
            for xy in direct_neighbors(*current):
                if xy not in paths and board.fits(xy, rel_coord):
                    paths[xy] = current
                    active.append(xy)
        return PathsTree(paths)


def find_shortest_path(board: Board, polyomino: Polyomino, target_position: tuple):
    # heuristic: taxicab distance
    def heuristic(p):
        return abs(target_position[0] - p[0]) + abs(target_position[1] - p[1])

    queue = PriorityQueue()
    position, rel_coord = polyomino.get_shape()
    paths = {position: None}
    g_score = {position: 0}

    queue.put((heuristic(position), position))
    while not queue.empty():
        current = queue.get()[1]
        tentative_g_score = g_score[current] + 1
        for xy in direct_neighbors(*current):
            if board.fits(xy, rel_coord) and tentative_g_score < g_score.get(
                xy, float("inf")
            ):
                paths[xy] = current
                g_score[xy] = tentative_g_score
                if xy == target_position:
                    return PathsTree(paths)
                queue.put((g_score[xy] + heuristic(xy), xy))
    return PathsTree(paths)


def shortest_sequence(board: Board, polyomino: Polyomino, target_position: tuple):
    return find_shortest_path(board, polyomino, target_position).get_moves(
        target_position
    )


def is_reachable(board: Board, polyomino: Polyomino, target_position: tuple):
    return target_position in find_shortest_path(board, polyomino, target_position)


def nearest_tile(board, destination):
    distance = {xy: 0 for xy in destination}
    active = deque(distance.keys())
    while active:
        current = active.popleft()
        for xy in direct_neighbors(*current):
            if board.is_blocked(*xy):
                continue
            if xy in distance:
                continue

            distance[xy] = distance[current] + 1
            active.append(xy)
            t = board.get_tile_at(*xy)
            if t:
                return t, distance[xy]
    return None


def is_reachable_area(board: Board, polyomino: Polyomino, target_area: set):
    # heuristic: taxicab distance to the center of target area
    c = center(target_area)

    def heuristic(p):
        return abs(c[0] - p[0]) + abs(c[1] - p[1])

    queue = PriorityQueue()
    position, rel_coord = polyomino.get_shape()
    paths = {position: None}

    queue.put((heuristic(position), position))
    while not queue.empty():
        current = queue.get()[1]
        if current in target_area:
            return PathsTree(paths)
        for xy in direct_neighbors(*current):
            if board.fits(xy, rel_coord) and xy not in paths:
                paths[xy] = current
                queue.put((heuristic(xy), xy))
    return False


def distance_to_area(board: Board, polyomino: Polyomino, target_area: set):
    # heuristic: taxicab distance to the center of target area
    c = center(target_area)

    def heuristic(p):
        return abs(c[0] - p[0]) + abs(c[1] - p[1])

    queue = PriorityQueue()
    position, rel_coord = polyomino.get_shape()
    paths = {position: None}
    g_score = {position: 0}

    queue.put((heuristic(position), position))
    while not queue.empty():
        current = queue.get()[1]
        tentative_g_score = g_score[current] + 1
        for xy in direct_neighbors(*current):
            if board.fits(xy, rel_coord) and tentative_g_score < g_score.get(
                xy, float("inf")
            ):
                paths[xy] = current
                g_score[xy] = tentative_g_score
                if xy in target_area:
                    return g_score[xy]
                queue.put((g_score[xy] + heuristic(xy), xy))
    return float("inf")


def center(points):
    x, y = zip(*points)
    return (max(x) + min(x)) // 2, (max(y) + min(y)) // 2


def _fits_at(shape1, shape2, x, y):
    for i, j in shape2:
        if not (x + i, y + j) in shape1:
            return False
    return True


# takes shapes as sets of relative coordinates
# returns true iff shape2 can be fit into shape1
def fits(shape1: Set[tuple], shape2: Set[tuple]):
    for x, y in shape1:
        if _fits_at(shape1, shape2, x, y):
            return True
    return False


# yields all possible positions, where shape2 fits in shape1
def get_packings(shape1: Set[tuple], shape2: Set[tuple]):
    for x, y in shape1:
        if _fits_at(shape1, shape2, x, y):
            yield x, y


# returns True iff a packing exists
def is_packable(container: Set[tuple], shapes: Iterable[Set[tuple]]):
    ascending = tuple(sorted(shapes, key=lambda s: len(s)))
    if sum(len(s) for s in ascending) > len(container):
        # to many tiles in combined shapes
        return False
    return _is_packable_recursive(container, ascending)


def _is_packable_recursive(container: Set[tuple], ascending):
    if not ascending:
        return True
    s = ascending[-1]
    for x, y in get_packings(container, s):
        new_container = container - {(dx + x, dy + y) for dx, dy in s}
        if _is_packable_recursive(new_container, ascending[:-1]):
            return True
    return False


def is_connected(shape: Set[tuple]):
    if not shape:
        return True  # empty shape is connected
    start = next(iter(shape))
    reachable = {start}
    active = deque([start])
    while active:
        current = active.popleft()
        for xy in direct_neighbors(*current):
            if xy in shape and xy not in reachable:
                reachable.add(xy)
                active.append(xy)
    return len(reachable) == len(shape)


def is_connected_by_glues(glues: Dict[tuple, Glues], rules: GlueRules):
    if not glues:
        return True
    current = next(iter(glues))
    visited = {current}
    active = [current]
    while active:
        current = active.pop()
        current_glues = glues[current]
        for d in Direction:
            neighbor = current[0] + d.vector()[0], current[1] + d.vector()[1]
            if neighbor in visited or neighbor not in glues:
                continue
            neighbor_glues = glues[neighbor]
            if rules.sticks(
                getattr(current_glues, d.value),
                getattr(neighbor_glues, d.inverse().value),
            ):
                visited.add(neighbor)
                active.append(neighbor)
    return len(visited) == len(glues)


def glue_connected_component(start: tuple, glues: Dict[tuple, Glues], rules: GlueRules):
    if not glues:
        return None
    current = start
    visited = {current}
    active = [current]
    while active:
        current = active.pop()
        current_glues = glues[current]
        for d in Direction:
            neighbor = current[0] + d.vector()[0], current[1] + d.vector()[1]
            if neighbor in visited or neighbor not in glues:
                continue
            neighbor_glues = glues[neighbor]
            if rules.sticks(
                getattr(current_glues, d.value),
                getattr(neighbor_glues, d.inverse().value),
            ):
                visited.add(neighbor)
                active.append(neighbor)
    return visited


def find_largest_glue_connected_component(glues: Dict[tuple, Glues], rules: GlueRules):
    largest = set()
    g = copy(glues)
    while g:
        if len(g) <= len(largest):
            return largest
        current = next(iter(g))
        component = glue_connected_component(current, g, rules)
        if len(component) > len(largest):
            largest = component
        for position in component:
            g.pop(position)
    return largest


def direct_path_between_configs(b: Board, state1, state2):
    state = b.get_state()
    board = Board(b.rows, b.cols, b.glue_rules)
    board.concrete = b.concrete

    board.restore_state(state1)
    position_to_glues1 = {p: t.glues for p, t in board._tile_at.items()}
    # position_to_glues1 = {p: tile.glues for p, tile in state1[0]}
    if hasattr(board, "fixed_tiles"):
        fixed_tile_positions1 = []
        for fixed_seed_tile in board.fixed_tiles:
            fixed_poly = fixed_seed_tile.parent
            fixed_tile_positions1 += [(t.x, t.y) for t in fixed_poly.get_tiles]
        for p in fixed_tile_positions1:
            position_to_glues1.pop(p)

    board.restore_state(state2)
    position_to_glues2 = {p: t.glues for p, t in board._tile_at.items()}
    if hasattr(board, "fixed_tiles"):
        fixed_tile_positions2 = []
        for fixed_seed_tile in board.fixed_tiles:
            fixed_poly = fixed_seed_tile.parent
            fixed_tile_positions2 += [(t.x, t.y) for t in fixed_poly.get_tiles]
        for p in fixed_tile_positions2:
            position_to_glues2.pop(p)

    if len(position_to_glues1) != len(position_to_glues2):
        b.restore_state(state)
        return None

    poly1 = Polyomino(
        tiles=[
            Tile(position=xy, glues=glues) for xy, glues in position_to_glues1.items()
        ]
    )
    poly2 = Polyomino(
        tiles=[
            Tile(position=xy, glues=glues) for xy, glues in position_to_glues2.items()
        ]
    )

    for position, tile in poly1.tiles.items():
        if position not in poly2.tiles or poly2.tiles[position].glues != tile.glues:
            b.restore_state(state)
            return None

    # mark positions that could be blocked by fixed polyominoes or their glues as blocked.
    if hasattr(board, "fixed_tiles"):
        board.polyominoes = []
        board._tile_at = {}
        board.fixed_tiles = []
        for p in fixed_tile_positions1:
            for nx, ny in direct_neighbors(*p):
                board.add_concrete(nx, ny)

    paths = find_shortest_path(board, poly1, poly2.position)
    if poly2.position in paths:
        b.restore_state(state)
        return [d.value for d in paths.get_moves(poly2.position)]
    else:
        b.restore_state(state)
        return None


def shorten_solution(instance, sequence):
    board = deepcopy(instance.initial_state)
    sequence = list(sequence)

    current_sequence_position = 0

    while current_sequence_position < len(sequence):
        current_state = board.get_state()
        last_occurence = current_sequence_position
        last_occurence_state = board.get_state()
        new_path = None

        for i in range(current_sequence_position, len(sequence)):
            board.step(sequence[i])
            board.activate_glues()
            s = board.get_state()
            p = direct_path_between_configs(board, current_state, s)
            if p is not None:
                last_occurence = i
                last_occurence_state = s
                new_path = p
        if new_path is None:
            current_sequence_position += 1
            board.restore_state(last_occurence_state)
            board.activate_glues()
            board.step(sequence[current_sequence_position - 1])
            continue

        # print("shortening", sequence[current_sequence_position:last_occurence + 1], "to:", new_path)
        sequence[current_sequence_position : last_occurence + 1] = new_path
        # print("new sequence", sequence)

        current_sequence_position = current_sequence_position + len(new_path) + 1

        board.restore_state(last_occurence_state)
        board.activate_glues()

        # print(board._tile_at.keys())
        try:
            board.step(sequence[current_sequence_position - 1])
            board.activate_glues()
        except IndexError:
            break
    return sequence
