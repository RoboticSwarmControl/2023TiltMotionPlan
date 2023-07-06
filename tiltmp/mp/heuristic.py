import heapq
import itertools
import math
import time
from abc import ABC
from collections import deque

import numpy as np

from tiltmp.core.algorithms import (
    center,
    find_shortest_path,
    nearest_tile,
    distance_to_area,
    reachable_set,
    compute_distances,
    compute_distance_within_set,
    breadth_first_distance,
)
from tiltmp.core.gridutil import direct_neighbors
from tiltmp.core.tumbletiles import Board, Polyomino, Tile

PRE_COMPUTATION_TIMEOUT = 605.0


class DistanceBasedHeuristic(ABC):
    def __init__(self, motion_planner, precomputed_distances=None):
        self._mp = motion_planner
        self._board = self._mp.board
        self._target_shape = self._mp.target_shape
        self._tiles_needed = self._target_shape.size
        if (
            precomputed_distances is not None
            and "precomputed_distances" in precomputed_distances
        ):
            self._distances = precomputed_distances["precomputed_distances"]
        else:
            self._distances = compute_distances(self._board, self._target_shape)

    def _n_closest(self):
        if self._tiles_needed == len(self._board.get_tiles()):
            return self._board.get_tiles()
        else:
            return heapq.nsmallest(
                self._tiles_needed,
                self._board.get_tiles(),
                key=lambda t: self._distances[t.x, t.y]
                if t.parent.can_reach
                else float("inf"),
            )


class GreatestDistanceHeuristic(DistanceBasedHeuristic):
    def __init__(self, motion_planner, **kwargs):
        super().__init__(motion_planner, kwargs)

    def __call__(self, score):
        n_closest = self._n_closest()
        if len(n_closest) < self._tiles_needed:
            return float("inf")
        return max(self._distances[(t.x, t.y)] for t in n_closest) + score


class AverageDistanceHeuristic(DistanceBasedHeuristic):
    def __init__(self, motion_planner, **kwargs):
        super().__init__(motion_planner, kwargs)

    def __call__(self, score):
        n_closest = self._n_closest()
        if len(n_closest) < self._tiles_needed:
            return float("inf")
        return (
            sum(self._distances[(t.x, t.y)] for t in n_closest) / self._tiles_needed
            + score
        )


class AverageDistanceAnchoringHeuristic(DistanceBasedHeuristic):
    def __init__(self, motion_planner, **kwargs):
        super().__init__(motion_planner, kwargs)

    def __call__(self, score):
        return (
            sum(self._distances[(t.x, t.y)] for t in self._mp.board.get_tiles())
            / len(self._mp.board.get_tiles())
            + score
        )


class MaxXYDistancesHeuristic(DistanceBasedHeuristic):
    def __init__(self, motion_planner, **kwargs):
        super().__init__(motion_planner, kwargs)
        self.left = min(t.x for t in self._target_shape.get_tiles())
        self.right = max(t.x for t in self._target_shape.get_tiles())
        self.down = min(t.y for t in self._target_shape.get_tiles())
        self.up = max(t.y for t in self._target_shape.get_tiles())

    def __call__(self, score):
        n_closest = self._n_closest()
        if len(n_closest) < self._tiles_needed:
            return float("inf")
        x_max = max(t.x for t in n_closest)
        x_min = min(t.x for t in n_closest)
        if x_min < self.left and x_max > self.right:
            x_moves = abs(x_max - self.right) + abs(x_min - self.left)
        else:
            x_moves = max(abs(x_max - self.right), abs(x_min - self.left))

        y_max = max(t.y for t in n_closest)
        y_min = min(t.y for t in n_closest)
        if y_min < self.down and y_max > self.up:
            y_moves = abs(y_max - self.up) + abs(y_min - self.down)
        else:
            y_moves = max(abs(y_max - self.up), abs(y_min - self.down))

        return x_moves + y_moves + score


# not admissible!
class WeightedDistanceSumHeuristic(DistanceBasedHeuristic):
    def __init__(self, motion_planner, exponent=2, **kwargs):
        super().__init__(motion_planner, kwargs)
        self._exponent = exponent

    def __call__(self, score):
        n_closest = self._n_closest()
        if len(n_closest) < self._tiles_needed:
            return float("inf")
        return sum(self._distances[(t.x, t.y)] ** self._exponent for t in n_closest)


class WeightedDistanceSumAnchoringHeuristic(DistanceBasedHeuristic):
    def __init__(self, motion_planner, exponent=2, **kwargs):
        super().__init__(motion_planner, kwargs)
        self._exponent = exponent

    def __call__(self, score):
        s = sum(
            self._distances[(t.x, t.y)] ** self._exponent
            for t in self._mp.board.get_tiles()
        )
        return s


class WeightedDistanceRepetitionPenaltyHeuristic(DistanceBasedHeuristic):
    def __init__(self, motion_planner, exponent=2, **kwargs):
        super().__init__(motion_planner, kwargs)
        self._exponent = exponent

    def __call__(self, score):
        node = self._mp._current_node
        if node is None:
            return 0

        n_closest = self._n_closest()
        if len(n_closest) < self._tiles_needed:
            return float("inf")

        previous_positions = []
        n = node
        for i in range(10):
            if n.parent is None:
                break
            n = n.parent
            try:
                previous_positions.append(n.tile_positions)
            except AttributeError:
                break

        value = 0
        repeated_tiles = 0
        for tile in n_closest:
            changed = False
            for positions in reversed(previous_positions):
                if positions[id(tile)] != (tile.x, tile.y):
                    changed = True
                if changed and positions[id(tile)] == (tile.x, tile.y):
                    repeated_tiles += 1
                    break
            value += self._distances[tile.x, tile.y] ** self._exponent
        value *= repeated_tiles
        return value


# not admissible!
class GreedyGreatestDistanceHeuristic(DistanceBasedHeuristic):
    def __init__(self, motion_planner, **kwargs):
        super().__init__(motion_planner, kwargs)

    def __call__(self, score):
        n_closest = self._n_closest()
        if len(n_closest) < self._tiles_needed:
            return float("inf")
        return max(self._distances[(t.x, t.y)] for t in n_closest)


class GreedyAverageDistanceHeuristic(DistanceBasedHeuristic):
    def __init__(self, motion_planner):
        super().__init__(motion_planner)

    def __call__(self, score):
        n_closest = self._n_closest()
        if len(n_closest) < self._tiles_needed:
            return float("inf")
        return sum(self._distances[(t.x, t.y)] for t in n_closest) / self._tiles_needed


class DistanceToNearestTile(DistanceBasedHeuristic):
    def __init__(self, motion_planner):
        super().__init__(motion_planner)
        self._destination = {(t.x, t.y) for t in self._target_shape.get_tiles()}

    def __call__(self, score):
        nearest, dist = nearest_tile(self._board, self._destination)
        seed_poly = nearest.parent
        tiles = [tile for tile in seed_poly.get_tiles()]

        distance = {(t.x, t.y): 0 for t in seed_poly.get_tiles()}
        active = deque(distance.keys())

        while len(tiles) < self._tiles_needed:
            current = active.popleft()
            for xy in direct_neighbors(*current):
                if self._board.is_blocked(*xy) or xy in distance:
                    continue
                distance[xy] = distance[current] + 1
                active.append(xy)
                t = self._board.get_tile_at(*xy)
                if t:
                    tiles.append(t)

        return sum((distance[(t.x, t.y)]) ** 2 for t in tiles)


# heuristic for MovePolyominoToAreaMotionPlanner
class DistancePolyominoToAreaHeuristic:
    def __init__(self, mp):
        self.mp = mp

    def __call__(self, score):
        c = center(self.mp.target_area)
        return len(find_shortest_path(self.mp.board, self.mp.poly, c).get_path(c))


# heuristic for single tile motion planner
class DistanceToPolyominoAndTargetAreaHeuristic2:
    def __init__(self, mp):
        self.mp = mp
        self._distances = mp.distances
        target_area_poly = Polyomino(
            tiles=(
                Tile(position=(x, y))
                for x, y in reachable_set(self.mp.board, self.mp.target_shape)
            )
        )
        self._distances_to_target_area = compute_distances(
            self.mp.board, target_area_poly
        )

    def __call__(self, score):
        tile_poly = Polyomino(tiles=[self.mp.tile])
        poly_x, poly_y = self.mp.poly.position
        dx, dy = self.mp.destination
        dest = (poly_x + dx, poly_y + dy)
        distance = self.get_distance(tile_poly, dest)
        taxicab_distance = abs(self.mp.tile.x - dest[0]) + abs(self.mp.tile.y - dest[1])
        min_moves = int((distance - taxicab_distance) / 2) + taxicab_distance
        distance_to_target_area = self._distances_to_target_area[poly_x, poly_y]
        tile_distance_to_target_area = self._distances_to_target_area[
            self.mp.tile.x, self.mp.tile.y
        ]
        return (
            max(distance_to_target_area + tile_distance_to_target_area, min_moves)
            + score
        )

    def get_distance(self, tile: Polyomino, destination):
        minimum = float("inf")
        distance_map = self._distances[tile.position]
        for coord in direct_neighbors(*destination):
            # destination can be in a wall
            if not self.mp.board.is_blocked(*coord):
                d = distance_map[coord]
                if d < minimum:
                    minimum = d
        return minimum - 1


# heuristic for single tile motion planner
class DistanceToPolyominoAndTargetAreaHeuristic:
    distances = {}
    target_area = set()
    MAX_DISTANCE_TO_TARGET_AREA = 4

    @staticmethod
    def pre_computation(board, target_shape):
        DistanceToPolyominoAndTargetAreaHeuristic.target_area = set()
        for x, y in reachable_set(board, target_shape):
            for dx, dy in target_shape.get_shape()[1]:
                DistanceToPolyominoAndTargetAreaHeuristic.target_area.add(
                    (x + dx, y + dy)
                )

        DistanceToPolyominoAndTargetAreaHeuristic._extend_target_area(board)

        DistanceToPolyominoAndTargetAreaHeuristic.distances = (
            DistanceToPolyominoAndTargetAreaHeuristic._compute_distance_map(board)
        )

    @staticmethod
    def _extend_target_area(board):
        target_area = DistanceToPolyominoAndTargetAreaHeuristic.target_area
        distance = {(x, y): 0 for (x, y) in target_area}
        active = deque(distance.keys())
        while active:
            current = active.popleft()
            if (
                distance[current]
                > DistanceToPolyominoAndTargetAreaHeuristic.MAX_DISTANCE_TO_TARGET_AREA
            ):
                continue
            for xy in direct_neighbors(*current):
                if not board.is_blocked(*xy) and xy not in distance:
                    distance[xy] = distance[current] + 1
                    active.append(xy)
                    target_area.add(xy)

    @staticmethod
    def _compute_distance_map(board):
        t0 = time.time()
        distances = {}
        target_area = DistanceToPolyominoAndTargetAreaHeuristic.target_area
        for x, y in target_area:
            if time.time() > t0 + PRE_COMPUTATION_TIMEOUT:
                raise TimeoutError("computation of distance map timed out")
            source = Polyomino(tiles=[Tile(position=(x, y))])
            distances[(x, y)] = compute_distance_within_set(board, source, target_area)
        print("precomputation done in: ", time.time() - t0)
        return distances

    def __init__(self, mp):
        self.mp = mp
        self._distances = self.__class__.distances
        target_area = set()
        for x, y in reachable_set(self.mp.board, self.mp.target_shape):
            for dx, dy in self.mp.target_shape.get_shape()[1]:
                target_area.add((x + dx, y + dy))
        target_area_poly = Polyomino(
            tiles=(Tile(position=(x, y)) for x, y in target_area)
        )
        self._distances_to_target_area = compute_distances(
            self.mp.board, target_area_poly
        )
        self.weighting_factor = target_area_poly.size
        # round up to the next power of 2
        self.weighting_factor = 2 ** math.ceil(math.log2(self.weighting_factor))

    def __call__(self, score):
        tile_poly = Polyomino(tiles=[self.mp.tile])
        poly_x, poly_y = self.mp.poly.position

        dx, dy = self.mp.destination
        dest = (poly_x + dx, poly_y + dy)

        distance_to_target_area = self._distances_to_target_area[poly_x, poly_y]
        tile_distance_to_target_area = self._distances_to_target_area[
            self.mp.tile.x, self.mp.tile.y
        ]
        dist_max = max(distance_to_target_area, tile_distance_to_target_area)
        if dist_max > self.__class__.MAX_DISTANCE_TO_TARGET_AREA:
            # Since configurations where the tile and polyomino are both inside the target area should usually be expanded first
            # , we apply a weighting factor proportional to the size of the target area
            return dist_max * self.weighting_factor + score
        else:
            distance = self.get_distance(tile_poly, dest)
            taxicab_distance = abs(self.mp.tile.x - dest[0]) + abs(
                self.mp.tile.y - dest[1]
            )
            min_moves = int((distance - taxicab_distance) / 2) + taxicab_distance
            return min_moves + score

    def get_distance(self, tile: Polyomino, destination):
        minimum = float("inf")
        distance_map = self._distances[tile.position]
        for coord in direct_neighbors(*destination):
            # destination can be in a wall
            if not self.mp.board.is_blocked(*coord):
                d = distance_map[coord]
                if d < minimum:
                    minimum = d
        return minimum


# heuristic for single tile motion planner
class DistanceToPolyominoHeuristic:
    distances = {}

    @staticmethod
    def pre_computation(board, target_shape):
        DistanceToPolyominoHeuristic.distances = (
            DistanceToPolyominoHeuristic._compute_distance_map(board)
        )

    @staticmethod
    def _compute_distance_map(board):
        t0 = time.time()
        distances = {}
        for x in range(board.cols):
            if time.time() > t0 + PRE_COMPUTATION_TIMEOUT:
                raise TimeoutError("computation of distance map timed out")
            for y in range(board.rows):
                if board.is_blocked(x, y):
                    continue
                source = Polyomino(tiles=[Tile(position=(x, y))])
                distances[(x, y)] = compute_distances(board, source)
        print("precomputation done in: ", time.time() - t0)
        return distances

    def __init__(self, mp):
        self.mp = mp
        self._distances = DistanceToPolyominoHeuristic.distances

    def __call__(self, score):
        tile_poly = Polyomino(tiles=[self.mp.tile])
        poly_x, poly_y = self.mp.poly.position
        dx, dy = self.mp.destination
        dest = (poly_x + dx, poly_y + dy)
        distance = self.get_distance(tile_poly, dest)
        taxicab_distance = abs(self.mp.tile.x - dest[0]) + abs(self.mp.tile.y - dest[1])
        min_moves = int((distance - taxicab_distance) / 2) + taxicab_distance
        return min_moves + score

    def get_distance(self, tile: Polyomino, destination):
        minimum = float("inf")
        distance_map = self._distances[tile.position]
        for coord in direct_neighbors(*destination):
            # destination can be in a wall
            if not self.mp.board.is_blocked(*coord):
                d = distance_map[coord]
                if d < minimum:
                    minimum = d
        return minimum - 1

    def get_previous_poly_position(self):
        node = self.mp._current_node
        if not node:
            return self.mp.poly.position
        try:
            n = node.polyomino_position
            return n
        except:
            return self.mp.poly.position


# heuristic for single tile motion planner
class GreedyDistanceToPolyominoHeuristic:
    distances = {}

    @staticmethod
    def pre_computation(board, target_shape):
        GreedyDistanceToPolyominoHeuristic.distances = (
            GreedyDistanceToPolyominoHeuristic._compute_distance_map(board)
        )

    @staticmethod
    def _compute_distance_map(board):
        t0 = time.time()
        distances = {}
        for x in range(board.cols):
            if time.time() > t0 + PRE_COMPUTATION_TIMEOUT:
                raise TimeoutError("computation of distance map timed out")
            for y in range(board.rows):
                if board.is_blocked(x, y):
                    continue
                source = Polyomino(tiles=[Tile(position=(x, y))])
                distances[(x, y)] = compute_distances(board, source)
        print("precomputation done in: ", time.time() - t0)
        return distances

    def __init__(self, mp):
        self.mp = mp
        self._distances = GreedyDistanceToPolyominoHeuristic.distances

    def __call__(self, score):
        tile_poly = Polyomino(tiles=[self.mp.tile])
        poly_x, poly_y = self.mp.poly.position
        dx, dy = self.mp.destination
        dest = (poly_x + dx, poly_y + dy)
        distance = self.get_distance(tile_poly, dest)
        return (
            int(distance / 2)
            + abs(self.mp.tile.x - dest[0])
            + abs(self.mp.tile.y - dest[1])
        )

    def get_distance(self, tile: Polyomino, destination):
        minimum = float("inf")
        distance_map = self._distances[tile.position]
        for coord in direct_neighbors(*destination):
            # destination can be in a wall
            if not self.mp.board.is_blocked(*coord):
                d = distance_map[coord]
                if d < minimum:
                    minimum = d
        return minimum

    def get_previous_poly_position(self):
        node = self.mp._current_node
        if not node:
            return self.mp.poly.position
        try:
            n = node.polyomino_position
            return n
        except:
            return self.mp.poly.position


class GreedyDistanceToFixedDestinationHeuristic:
    @staticmethod
    def pre_computation(board, target_shape):
        pass

    def _compute_distances(self):
        return breadth_first_distance(
            {self.destination},
            lambda xy: direct_neighbors(*xy),
            is_valid_neighbor=lambda xy: self._passable(*xy),
        )

    def _passable(self, x, y):
        board = self.mp.board
        if board.is_blocked(x, y):
            return False
        if (x, y) in self.blocked:
            return False
        return True

    """returns the set of all the positions blocked by fixed polyominoes"""

    def _blocked_by_fixed_polyominoes(self):
        blocked = set()
        board = self.mp.board
        tile = self.mp.tile
        if not hasattr(board, "fixed_tiles"):
            return blocked
        for fixed_polyomino in {t.parent for t in board.fixed_tiles}:
            for t in fixed_polyomino.get_tiles():
                if tile.x == t.x and tile.y == tile.y:
                    blocked.add((t.x, t.y))
                for nx, ny in direct_neighbors(t.x, t.y):
                    if board._glueable(t, Tile(position=(nx, ny), glues=tile.glues)):
                        blocked.add((nx, ny))
        return blocked

    def __init__(self, mp):
        self.mp = mp
        poly_x, poly_y = self.mp.poly.position
        dx, dy = self.mp.destination
        self.blocked = self._blocked_by_fixed_polyominoes()
        self.destination = (poly_x + dx, poly_y + dy)
        self._distances = self._compute_distances()

    def __call__(self, score):
        t = self.mp.tile
        return self._distances.get((t.x, t.y), float("inf"))


class DistanceToFixedDestinationHeuristic(GreedyDistanceToFixedDestinationHeuristic):
    def __call__(self, score):
        return super().__call__(score) + score


# useful when there are just enough tiles and it does not matter where on the board the shape is build.
def average_distance_to_center(board: Board, target_shape: Polyomino, score):
    c = center((t.x, t.y) for t in board.get_tiles())
    tile_count = 0
    distance = {c: 0}
    active = deque(distance.keys())
    while active:
        current = active.popleft()
        t = board.get_tile_at(*current)
        if t and t.parent.can_reach:
            tile_count += 1
        if target_shape.size <= tile_count:
            return (
                sum(distance[t.x, t.y] for t in board.get_tiles()) / target_shape.size
                + score
            )
        for xy in direct_neighbors(*current):
            if not board.is_blocked(*xy) and xy not in distance:
                distance[xy] = distance[current] + 1
                active.append(xy)
    return float("inf")


HEURISTICS = {
    "Greatest Distance": GreatestDistanceHeuristic,
    "Average Distance": AverageDistanceHeuristic,
    "Weighted Sum of Distances": WeightedDistanceSumHeuristic,
    "Greedy Greatest Distance": GreedyGreatestDistanceHeuristic,
    "Greedy Average Distance": GreedyAverageDistanceHeuristic,
    "Distance to Nearest Tile": DistanceToNearestTile,
    "Repetition Penalty": WeightedDistanceRepetitionPenaltyHeuristic,
}

SINGLE_TILE_HEURISTICS = {
    "Minimum Moves": DistanceToPolyominoHeuristic,
    "Minimum Moves and Distance to Target Area": DistanceToPolyominoAndTargetAreaHeuristic,
    "Greedy Distance": GreedyDistanceToPolyominoHeuristic,
    "Distance to fixed Destination": DistanceToFixedDestinationHeuristic,
    "Greedy distance to fixed destination": GreedyDistanceToFixedDestinationHeuristic,
}
