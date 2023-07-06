import time
from queue import Queue

import numpy as np
from abc import ABC, abstractmethod

import tiltmp.core.tumbletiles as TT
from tiltmp.core.algorithms import *
from tiltmp.core.build_order import BuildOrderPlanner
from tiltmp.mp.heuristic import *
from tiltmp.mp.pruner import *


DIRECTIONS = tuple(Direction)


class Instance:
    def __init__(self, initial_state: TT.Board, target_shape: TT.Polyomino):
        self.initial_state = initial_state
        self.target_shape = target_shape


class Node:
    def __init__(self, parent, last_move, state):
        self.parent = parent
        self.last_move = last_move
        self.state = state
        self.candidate_moves = DIRECTIONS

    # for use in priority queue
    def __lt__(self, other):
        return True


class MotionPlanner(ABC):
    def __init__(self, instance: Instance):
        self.instance = instance
        self.board = deepcopy(instance.initial_state)
        self.target_shape = instance.target_shape
        self._pruners = []
        self._stopped = False

    def stop(self):
        self._stopped = True

    def add_pruner(self, pruner: Pruner):
        self._pruners += [pruner]
        pruner.setup(self.board, self.target_shape)

    @abstractmethod
    def solve(self):
        pass

    @abstractmethod
    def extract_solution(self):
        pass


class BFSMotionPlanner(MotionPlanner):
    def __init__(self, instance: Instance):
        super().__init__(instance)
        self.board = deepcopy(instance.initial_state)
        self.target_shape = instance.target_shape
        self._pruners = []
        self._stop_condition = self._initial_stop_condition()

        self._solution_node = None
        self._number_of_nodes = 0
        self._current_node = None
        self._active_nodes = Queue()
        self._active_nodes.put(self._create_node(None))
        self._visited = set()

    def _initial_stop_condition(self):
        if self.target_shape.size == len(self.board.get_tiles()) and not hasattr(
            self.board, "fixed_tiles"
        ):
            return BFSMotionPlanner.NoLeftoversStopCondition(self)
        else:
            return BFSMotionPlanner.DefaultStopCondition(self)

    def set_stop_condition(self, stop_condition):
        self._stop_condition = stop_condition

    class NoLeftoversStopCondition:
        def __init__(self, motion_planner):
            self.mp = motion_planner
            self._target_area = reachable_set(self.mp.board, self.mp.target_shape)
            self._solution_polyomino = None

        def extract_solution(self):
            if self.mp._solution_node is None:
                return None
            end_sequence = shortest_sequence(
                self.mp.board, self._solution_polyomino, self.mp.target_shape.position
            )
            return self.mp.get_control_sequence(self.mp._solution_node) + [
                d.value for d in end_sequence
            ]

        def is_finished(self):
            for polyomino in self.mp.board.polyominoes:
                if (
                    polyomino.shape_equals(self.mp.target_shape)
                    and polyomino.position in self._target_area
                ):
                    self._solution_polyomino = deepcopy(polyomino)
                    return True
            return False

    class DefaultStopCondition:
        def __init__(self, motion_planner):
            self.mp = motion_planner

        def extract_solution(self):
            if self.mp._solution_node is None:
                return None
            return self.mp.get_control_sequence(self.mp._solution_node)

        def is_finished(self):
            for polyomino in self.mp.board.polyominoes:
                if (
                    polyomino.position == self.mp.target_shape.position
                    and polyomino.shape_equals(self.mp.target_shape)
                ):
                    return True
            return False

    class AnchoringStopCondition:
        def __init__(self, motion_planner):
            self.mp = motion_planner
            for t in self.mp.target_shape.get_tiles():
                if not self.mp.board.concrete[t.x, t.y]:
                    raise ValueError(
                        "target shape has to be concrete in order for anchoring to work"
                    )

        def extract_solution(self):
            if self.mp._solution_node is None:
                return None
            return self.mp.get_control_sequence(self.mp._solution_node)

        def is_finished(self):
            for polyomino in self.mp.board.adjacent_polyominoes(self.mp.target_shape):
                blocked = True
                for direction in Direction:
                    # is poly blocked by concrete or walls in every direction?
                    is_wall = {
                        Direction.N: (lambda board, x, y: y < 0),
                        Direction.W: (lambda board, x, y: x < 0),
                        Direction.S: (lambda board, x, y: y >= board.rows),
                        Direction.E: (lambda board, x, y: x >= board.cols),
                    }[direction]
                    if not self.mp.board.polyomino_is_blocked(
                        polyomino, direction, is_wall
                    ):
                        blocked = False
                        break
                if blocked:
                    return True
            return False

    def add_pruner(self, pruner: Pruner):
        self._pruners += [pruner]
        pruner.setup(self.board, self.target_shape)

    @property
    def number_of_nodes(self):
        return self._number_of_nodes

    def _create_node(self, direction):
        self._number_of_nodes += 1
        return Node(self._current_node, direction, self.board.get_state())

    def _load_node(self, node: Node):
        self._current_node = node
        self.board.restore_state(node.state)

    def solve(self, max_nodes=None):
        if self.is_finished():
            self._solution_node = self._create_node(None)
            return []
        if max_nodes:
            return self._solve_with_max_nodes(max_nodes)
        while (
            not self._active_nodes.empty()
            and self._solution_node is None
            and not self._stopped
        ):
            self._expand(self._active_nodes.get())
        return self.extract_solution()

    def _solve_with_max_nodes(self, max_nodes):
        while (
            not self._active_nodes.empty()
            and self._solution_node is None
            and not self._stopped
        ):
            if self.number_of_nodes > max_nodes:
                break
            self._expand(self._active_nodes.get())
        return self.extract_solution()

    def get_solution_board(self):
        if self._solution_node is None:
            return None
        b = deepcopy(self.board)
        b.restore_state(self._solution_node.state)
        return b

    def _expand(self, node):
        for direction in DIRECTIONS:
            self._load_node(node)
            self._step(direction)
        del self._current_node.state

    def _step(self, direction):
        if self.board.step(direction.value):
            h = hash(self.board)
            if h in self._visited:
                return
            changed = self.board.activate_glues()
            if any(pruner.is_prunable(changed) for pruner in self._pruners):
                return
            if self.is_finished():
                self._solution_node = self._create_node(direction)
            self._visited.add(h)
            self._active_nodes.put(self._create_node(direction))

    def extract_solution(self):
        return self._stop_condition.extract_solution()

    @staticmethod
    def get_control_sequence(node):
        control_sequence = []
        while node.parent is not None:
            control_sequence += [node.last_move.value]
            node = node.parent
        return list(reversed(control_sequence))

    def is_finished(self):
        return self._stop_condition.is_finished()


class HeuristicMotionPlanner(BFSMotionPlanner):
    def __init__(
        self,
        instance: Instance,
        heuristic=GreatestDistanceHeuristic,
        precomputed_distances=None,
    ):
        super().__init__(instance)
        self.score = {hash(self.board): 0.0}
        self._current_score = 0

        if precomputed_distances is not None and issubclass(
            heuristic, DistanceBasedHeuristic
        ):
            self.heuristic = heuristic(
                self, precomputed_distances=precomputed_distances
            )
        else:
            self.heuristic = heuristic(self)

        self._active_nodes = PriorityQueue()

        first_node = self._create_node(None)
        self.best_node = first_node
        self.best_heuristic_value = self.heuristic(0)

        self._active_nodes.put((self.best_heuristic_value, first_node))

    def _expand_reachable_set(self, node):
        self._load_node(node)
        previous_score = self.score[hash(self.board)]
        poly_all = Polyomino(
            tiles=[tile for poly in self.board.polyominoes for tile in poly.get_tiles()]
        )
        for dx, dy, depth, n in expand_reachable_set(self.board, poly_all, node):
            self._load_node(node)
            self.board._move_polyominoes(self.board.polyominoes, dx, dy)
            h = hash(self.board)
            s = previous_score + depth
            if s >= self.score.get(h, float("inf")):
                continue
            self.score[h] = s
            n.state = self.board.get_state()
            priority = self.heuristic(s)
            self._active_nodes.put((priority, n))
            self._number_of_nodes += 1

    def get_best_node(self):
        return self.best_node, self.best_heuristic_value

    def _expand(self, node):
        node = node[1]
        self._current_score = None
        for direction in node.candidate_moves:
            self._load_node(node)
            if self._current_score is None:
                self._current_score = self.score[hash(self.board)]
            self._step(direction)
        if node is not self.best_node:
            del node.state
            del node.candidate_moves

    def _step(self, direction):
        if not self.board.step(direction.value):
            return  # step did not change anything
        h = hash(self.board)
        if self._current_score + 1 >= self.score.get(h, float("inf")):
            return  # shorter path to this board state is known
        changed = self.board.activate_glues()
        if any(pruner.is_prunable(changed) for pruner in self._pruners):
            self.score[h] = float("inf")
            return  # it can be proven that this branch can not lead to the solution
        self.score[h] = self._current_score + 1
        if self.is_finished():
            self._solution_node = self._create_node(direction)
        priority = self.heuristic(self.score[h])
        if priority == float("inf"):
            return
        n = self._create_node(direction)
        self._active_nodes.put((priority, n))

        if priority < self.best_heuristic_value:
            self.best_node = n
            self.best_heuristic_value = priority

        # self._expand_reachable_set(n)


class PolyominoToAreaMotionPlanner(HeuristicMotionPlanner):
    def __init__(self, instance, poly, target_area):
        self.poly = poly
        super().__init__(instance)
        self.poly = self.board.get_tile_at(*poly.position).parent
        self.target_area = target_area
        self._stop_condition = (
            PolyominoToAreaMotionPlanner.PolyominoInAreaStopCondition(self)
        )
        self.heuristic = DistancePolyominoToAreaHeuristic(self)
        self._active_nodes = PriorityQueue()
        self._active_nodes.put((self.heuristic(0), self._create_node(None)))

    def _create_node(self, direction):
        node = super()._create_node(direction)
        node.polyomino_position = self.poly.position
        return node

    def _load_node(self, node: Node):
        super()._load_node(node)
        self.poly = self.board.get_tile_at(*node.polyomino_position).parent

    class PolyominoInAreaStopCondition:
        def __init__(self, motion_planner):
            self.mp = motion_planner

        def extract_solution(self):
            if self.mp._solution_node is None:
                return None
            return self.mp.get_control_sequence(self.mp._solution_node)

        def is_finished(self):
            return self.mp.poly.position in self.mp.target_area


class SingleTileMotionPlanner(HeuristicMotionPlanner):
    def __init__(
        self,
        instance: Instance,
        tile,
        poly,
        destination,
        offset,
        heuristic=DistanceToPolyominoAndTargetAreaHeuristic,
    ):
        self.poly = poly
        self.tile = tile
        self.offset = offset
        super().__init__(instance)
        # board gets copied. Get the corresponding new tile and poly objects
        self.poly = self.board.get_tile_at(*poly.position).parent
        self.tile = self.board.get_tile_at(tile.x, tile.y)
        self.destination = destination  # destination of tile relative to the polyomino

        # TODO Is target shape connected and do the glues work?
        self._stop_condition = SingleTileMotionPlanner.TileAtDestination(self)
        self.heuristic = heuristic(self)
        self.add_pruner(WrongTilesCombinedPruner(self))
        if not hasattr(self.board, "fixed_tiles"):
            self.add_pruner(TargetUnreachablePruner(self))
        self._active_nodes = PriorityQueue()
        self._active_nodes.put((self.heuristic(0), self._create_node(None)))

    class TileAtDestination:
        def __init__(self, motion_planner):
            self.mp = motion_planner

        def extract_solution(self):
            if self.mp._solution_node is None:
                return None
            return self.mp.get_control_sequence(self.mp._solution_node)

        def is_finished(self):
            # check position relative to the previous corner tile of the target poly
            previous_corner_tile = self.mp.poly.tiles[(0, 0)]
            return (
                self.mp.tile.x == previous_corner_tile.x + self.mp.destination[0]
                and self.mp.tile.y == previous_corner_tile.y + self.mp.destination[1]
            )

    def _compute_legal_poly_positions(self):
        shape = set(self.poly.get_shape()[1])
        shape.add(self.destination)
        x, y = self.target_shape.position
        next_poly = Polyomino(
            tiles=(Tile(position=(x + dx, y + dy)) for dx, dy in shape)
        )
        return reachable_set(self.board, next_poly)

    def _create_node(self, direction):
        node = super()._create_node(direction)
        node.polyomino_position = self.poly.position
        node.tile_position = (self.tile.x, self.tile.y)
        return node

    def _expand_reachable_set(self, node):
        self._load_node(node)
        previous_score = self.score[hash(self.board)]
        poly_all = Polyomino(
            tiles=[tile for poly in self.board.polyominoes for tile in poly.get_tiles()]
        )
        for dx, dy, depth, n in expand_reachable_set(self.board, poly_all, node):
            self._load_node(node)
            self.board._move_polyominoes(self.board.polyominoes, dx, dy)
            h = hash(self.board)
            s = previous_score + depth
            if s >= self.score.get(h, float("inf")):
                continue
            self.score[h] = s
            n.state = self.board.get_state()
            n.polyomino_position = (
                node.polyomino_position[0] + dx,
                node.polyomino_position[1] + dy,
            )
            n.tile_position = node.tile_position[0] + dx, node.tile_position[1] + dy
            priority = self.heuristic(s)
            self._active_nodes.put((priority, n))
            self._number_of_nodes += 1

    def _load_node(self, node: Node):
        super()._load_node(node)
        self.poly = self.board.get_tile_at(*node.polyomino_position).parent
        self.tile = self.board.get_tile_at(*node.tile_position)


class OneTileAtATimeMotionPlanner(MotionPlanner):
    def __init__(
        self,
        instance: Instance,
        single_tile_heuristic=DistanceToPolyominoAndTargetAreaHeuristic,
    ):
        super().__init__(instance)
        self._initial_board_state = self.board.get_state()
        self.single_tile_heuristic = single_tile_heuristic
        self.poly = None
        try:
            self.build_order_planner = BuildOrderPlanner(self.board, self.target_shape)
        except TimeoutError as e:
            self.number_of_nodes = 0
            self.solution = None
            raise e
        (x, y), tile = self.build_order_planner.get_next_tile(None, (0, 0))
        self.poly = tile.parent
        # difference of the position of the final polyomino and the current sub-polyomino
        self.offset = (x, y)

        self.sub_motion_planner = None
        self.number_of_nodes = 0
        self.solution = None

    def next_build_order(self):
        self.solution = []
        self.build_order_planner.change_build_order()
        self.board.restore_state(self._initial_board_state)
        self.poly = None
        (x, y), tile = self.build_order_planner.get_next_tile(None, (0, 0))
        self.poly = tile.parent
        self.offset = (x, y)

    def _find_nearest_tile(self, destination_shape):
        distance = {xy: 0 for xy in destination_shape}
        active = deque(distance.keys())
        while active:
            current = active.popleft()
            t = self.board.get_tile_at(*current)
            if t and t.parent is not self.poly:
                return t, distance[current]
            for xy in direct_neighbors(*current):
                if self.board.is_blocked(*xy):
                    continue
                if xy in distance:
                    continue
                distance[xy] = distance[current] + 1
                active.append(xy)
        return None

    def _get_next_destination(self, x, y):
        destination = (x - self.offset[0], y - self.offset[1])
        # update offset
        if destination < (0, 0):
            self.offset = x, y
        return destination

    def solve(self):
        try:
            self.single_tile_heuristic.pre_computation(self.board, self.target_shape)
        except TimeoutError:
            self.solution = None
            return None
        self.solution = []

        while not self.build_order_planner.finished() and not self._stopped:
            instance = Instance(self.board, self.target_shape)

            (x, y), tile = self.build_order_planner.get_next_tile(
                self.poly, self.offset
            )
            destination = self._get_next_destination(x, y)
            assert tile is not None
            self.sub_motion_planner = SingleTileMotionPlanner(
                instance,
                tile,
                self.poly,
                destination,
                self.offset,
                heuristic=self.single_tile_heuristic,
            )
            solution = self.sub_motion_planner.solve()
            self.number_of_nodes += self.sub_motion_planner.number_of_nodes
            if solution is None:
                try:
                    self.next_build_order()
                    continue
                except StopIteration:
                    self.solution = None
                    return None
                except TimeoutError:
                    self._stopped = True
                    break
            for direction in solution:
                self.board.step(direction)
            self.board.activate_glues()
            self.poly = max(self.board.polyominoes, key=lambda p: p.size)  # update poly
            self.solution += solution

        if self._stopped:
            self.solution = None
            return None

        self.solution += (
            d.value
            for d in shortest_sequence(
                self.board, self.poly, self.target_shape.position
            )
        )
        return self.extract_solution()

    def stop(self):
        super().stop()
        if self.sub_motion_planner:
            self.sub_motion_planner.stop()

    def extract_solution(self):
        if self.solution is not None:
            return self.solution


# expands the node to every edge of the reachable set
def expand_reachable_set(board, polyomino, node):
    position, rel_coord = polyomino.get_shape()
    # maps position to previous position on the shortest path
    visited = {position}
    # (position, node, depth)
    active = deque([(position, node, 0)])
    while active:
        current, current_node, depth = active.popleft()
        directions = []
        for direction in Direction:
            xy = neighbor(current, direction)
            if xy in visited:
                continue
            if board.fits(xy, rel_coord):
                visited.add(xy)
                n = Node(current_node, direction, None)
                active.append((xy, n, depth + 1))
            else:
                directions += [direction]
        if directions:
            current_node.candidate_moves = directions
            dx, dy = current[0] - position[0], current[1] - position[1]
            yield dx, dy, depth, current_node


def get_anchoring_motion_planner(instance: Instance):
    mp = HeuristicMotionPlanner(
        instance, heuristic=WeightedDistanceSumAnchoringHeuristic
    )
    anchoring = BFSMotionPlanner.AnchoringStopCondition(mp)
    mp.set_stop_condition(anchoring)
    return mp


def get_motion_planner(
    instance: Instance, heuristic=GreatestDistanceHeuristic, precomputed_distances=None
):
    if instance.initial_state.number_of_tiles() == instance.target_shape.size:
        mp = HeuristicMotionPlanner(
            instance, heuristic=heuristic, precomputed_distances=precomputed_distances
        )
        mp.add_pruner(NotEnoughTilesNoLeftoversPruner())
        mp.add_pruner(PackingNoLeftoversPruner(3))
    else:
        mp = HeuristicMotionPlanner(
            instance, heuristic=heuristic, precomputed_distances=precomputed_distances
        )
        mp.add_pruner(NotEnoughTilesPruner())
        mp.add_pruner(PackingPruner())
    if hasattr(instance.initial_state, "fixed_tiles"):
        mp.add_pruner(TilesGluedOutsideTargetAreaPruner())
    return mp
