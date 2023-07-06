import bisect
import itertools
import random
from copy import copy, deepcopy
import time
from queue import PriorityQueue

import numpy as np

from tiltmp.core.algorithms import compute_distances
from tiltmp.core.build_order import get_blueprint_with_glue_types
from tiltmp.core.serialization import read_instance
from tiltmp.core.tumbletiles import Board, Polyomino, Direction, Tile
from tiltmp.mp.heuristic import (
    WeightedDistanceSumHeuristic,
    DistanceBasedHeuristic,
    GreedyGreatestDistanceHeuristic,
)
from tiltmp.mp.motionplanner import (
    Instance,
    MotionPlanner,
    BFSMotionPlanner,
    get_motion_planner,
)
import networkx as nx


class RTTNode:
    def __init__(self, config, parent, sequence):
        self.config = config
        self.parent = parent
        # sequence from parent to this configuration
        self.sequence = sequence
        self.feasible = True
        self.distance_to_target = None

    def __lt__(self, other):
        return self.distance_to_target < other.distance_to_target


class Configuration:
    def __init__(self, tile_mapping, board, fixed_tiles=()):
        self.tiles = tile_mapping
        self.fixed_tiles_positions = fixed_tiles
        self.board = board

    def apply(self):
        self.board._tile_at = {}
        self.board.polyominoes = []
        for position, tile in self.tiles.items():
            tile.x, tile.y = position
            self.board.add(Polyomino(tiles=[tile]))
        if self.fixed_tiles_positions and hasattr(self.board, "fixed_tiles"):
            self.board.fixed_tiles = {
                self.tiles[position] for position in self.fixed_tiles_positions
            }
        self.board.activate_glues()

    def __hash__(self):
        return hash(
            tuple(sorted((tx, ty, t.glues) for (tx, ty), t in self.tiles.items()))
        )

    def __eq__(self, other):
        if len(self.fixed_tiles_positions) != len(other.fixed_tiles_positions):
            return False
        for position in self.fixed_tiles_positions:
            if position not in other.fixed_tiles_positions:
                return False
        for position, tile in self.tiles.items():
            if position not in other.tiles:
                return False
            if other.tiles[position].glues != tile.glues:
                return False
        return True

    @staticmethod
    def from_board(board):
        if hasattr(board, "fixed_tiles"):
            return Configuration(
                copy(board._tile_at),
                board,
                fixed_tiles=[(t.x, t.y) for t in board.fixed_tiles],
            )
        return Configuration(copy(board._tile_at), board)


def get_random_configuration(board: Board):
    if hasattr(board, "fixed_tiles"):
        tiles = [
            tile for tile in board.get_tiles() if tile if tile not in board.fixed_tiles
        ]
        seed_tile_positions = [(t.x, t.y) for t in board.fixed_tiles]
        open_positions = [
            (x, y)
            for x, y in np.argwhere(board.concrete == 0)
            if (x, y) not in seed_tile_positions
        ]
    else:
        tiles = [tile for tile in board.get_tiles() if tile]
        seed_tile_positions = ()
        open_positions = [(x, y) for x, y in np.argwhere(board.concrete == 0) if (x, y)]

    tile_positions = random.sample(open_positions, len(tiles))

    mapping = dict(zip(tile_positions, tiles))
    if hasattr(board, "fixed_tiles"):
        for tile in board.fixed_tiles:
            mapping[(tile.x, tile.y)] = tile
    return Configuration(mapping, board, fixed_tiles=seed_tile_positions)


def perfect_matching_with_shorter_edges_exists(g, top_nodes, threshold):
    # construct subgraph
    subgraph = nx.Graph(g)
    for edge in g.edges:
        if g.edges[edge]["weight"] > threshold:
            subgraph.remove_edge(edge[0], edge[1])

    matching = nx.bipartite.hopcroft_karp_matching(subgraph, top_nodes=top_nodes)
    if len(matching) < len(subgraph.nodes):
        return False
    else:
        return matching


def bottleneck_matching_old(
    g, top_nodes, max_iterations=10, max_bottleneck=float("inf")
):
    # get weights
    weights = nx.get_edge_attributes(g, "weight")
    sorted_weights = np.sort(np.fromiter(weights.values(), dtype=float))

    left = 0
    right = len(sorted_weights)

    if max_bottleneck != float("inf"):
        if not perfect_matching_with_shorter_edges_exists(g, top_nodes, max_bottleneck):
            return float("inf")
        else:
            right = np.searchsorted(sorted_weights, max_bottleneck)

    i = 0
    while left < right and i < max_iterations:
        mid = int((right + left) / 2)
        if perfect_matching_with_shorter_edges_exists(
            g, top_nodes, sorted_weights[mid]
        ):
            left = mid + 1
        else:
            right = mid
        i += 1

    return None, sorted_weights[right - 1]


def bottleneck_matching(g, top_nodes, max_iterations=10, max_bottleneck=float("inf")):
    # get weights
    weights = nx.get_edge_attributes(g, "weight")
    sorted_weights = np.sort(np.fromiter(weights.values(), dtype=float))

    left = 0
    right = len(sorted_weights)

    if max_bottleneck != float("inf"):
        if not perfect_matching_with_shorter_edges_exists(g, top_nodes, max_bottleneck):
            return None, float("inf")
        else:
            right = np.searchsorted(sorted_weights, max_bottleneck)

    i = 0
    bottleneck_matching = None
    while left < right and i < max_iterations:
        mid = int(np.floor((right + left) / 2))
        matching = perfect_matching_with_shorter_edges_exists(
            g, top_nodes, sorted_weights[mid]
        )
        if matching:
            right = mid
            bottleneck_matching = matching
        else:
            left = mid + 1
        i += 1
    return bottleneck_matching, sorted_weights[left]


def bottleneck_weighted_sum_matching(
    config1, config2, max_iterations=10, max_bottleneck=float("inf")
):
    g, top_nodes = construct_taxicab_distance_graph(config1, config2)
    matching = bottleneck_matching(g, top_nodes, max_iterations, max_bottleneck)[0]
    result = 0
    used_edges = set()
    for n1, n2 in matching.items():
        if (n2, n1) in used_edges:
            continue
        result += g.edges[(n1, n2)]["weight"] ** 2
        used_edges.add((n1, n2))
    return result


def taxicab_distance(x, y):
    return abs(x[0] - y[0]) + abs(x[1] - y[1])


def hausdorff_distance(
    config1, config2, max_bottleneck=float("inf"), distance_func=taxicab_distance
):
    overall_max = 0
    for p1, t1 in config1.tiles.items():
        t1_min = float("inf")
        for p2, t2 in config2.tiles.items():
            if t1.glues == t2.glues:
                t1_min = min(distance_func(p1, p2), t1_min)
                if t1_min < overall_max:
                    break
        overall_max = max(t1_min, overall_max)

    for p1, t1 in config2.tiles.items():
        t1_min = float("inf")
        for p2, t2 in config1.tiles.items():
            if t1.glues == t2.glues:
                t1_min = min(distance_func(p1, p2), t1_min)
                if t1_min < overall_max:
                    break
    return overall_max


def bottleneck_edge_length(
    config1,
    config2,
    max_iterations=10,
    max_bottleneck=float("inf"),
    distance_func=taxicab_distance,
):
    g, top_nodes = construct_matching_graph(config1, config2, distance_func)
    return bottleneck_matching(g, top_nodes, max_iterations, max_bottleneck)[1]


def construct_matching_graph(config1, config2, distance_func):
    g = nx.Graph()
    top_nodes = [(p, 1) for p in config1.tiles.keys()]
    bottom_nodes = [(p, 2) for p in config2.tiles.keys()]
    g.add_nodes_from(top_nodes, bipartite=0)
    g.add_nodes_from(bottom_nodes, bipartite=1)

    for (p1, t1), (p2, t2) in itertools.product(
        config1.tiles.items(), config2.tiles.items()
    ):
        if t1.glues == t2.glues:
            weight = distance_func(p1, p2)
            g.add_edge((p1, 1), (p2, 2), weight=weight)

    return g, top_nodes


def greedy_bottleneck(config1, config2, max_bottleneck=float("inf")):
    def taxicab_distance(x, y):
        return abs(x[0] - y[0]) + abs(x[1] - y[1])

    edge_queue = PriorityQueue()
    matched = set()
    edges = []
    for (p1, t1), (p2, t2) in itertools.product(
        config1.tiles.items(), config2.tiles.items()
    ):
        if t1.glues == t2.glues:
            edge_queue.put((taxicab_distance(p1, p2), (p1, 1), (p2, 2)))

    needed = len(config1.tiles) * 2
    max_weight = 0
    while len(matched) < needed and not edge_queue.empty():
        weight, p1, p2 = edge_queue.get()
        if weight > max_bottleneck:
            return float("inf")
        if (p1, 1) not in matched and (p2, 2) not in matched:
            max_weight = max(max_weight, weight)
            matched.update({(p1, 1), (p2, 2)})
            edges.append((p1, p2))
    return max_weight


def bottleneck_edge_length_real_distance(
    config1, config2, max_iterations=10, max_bottleneck=float("inf")
):
    g, top_nodes = construct_real_distance_graph(config1, config2)
    return bottleneck_matching(g, top_nodes, max_iterations, max_bottleneck)[1]


DISTANCES = None


def _compute_distance_map(board):
    t0 = time.time()
    distances = {}
    for x in range(board.cols):
        for y in range(board.rows):
            if board.is_blocked(x, y):
                continue
            source = Polyomino(tiles=[Tile(position=(x, y))])
            distances[(x, y)] = compute_distances(board, source)
    print("precomputation done in: ", time.time() - t0)
    global DISTANCES
    DISTANCES = distances


class RRTSolver(MotionPlanner):
    def __init__(
        self, instance, bias=0.05, distance_metric=hausdorff_distance, max_nodes=None
    ):
        super().__init__(instance)
        self._target_distances = compute_distances(self.board, self.target_shape)
        _compute_distance_map(self.board)
        self._target_shape_positions = [
            (t.x, t.y) for t in self.target_shape.get_tiles()
        ]
        self._solution_node = None
        self.nodes = []
        self.visited = set()
        self.max_nodes = max_nodes
        initial_node = RTTNode(Configuration.from_board(self.board), None, "")
        initial_node.distance_to_target = self.distance_to_target(initial_node.config)
        self.add_node(initial_node)
        if initial_node.distance_to_target == float("inf"):
            raise ValueError("Tiles can not produce target polyomino")
        self.distance_metric = distance_metric
        self.bias = bias

    @property
    def number_of_nodes(self):
        return len(self.nodes)

    def add_node(self, node):
        if hash(node.config) in self.visited:
            return False
        self.visited.add(hash(node.config))
        bisect.insort_left(self.nodes, node)
        return True

    @property
    def clostest_to_target(self):
        for node in self.nodes:
            if node.feasible:
                return node
        return self.nodes[0]

    def expand_random(self):
        random_config = get_random_configuration(self.board)
        closest, distance = self.find_closest_node(random_config)
        new_node = self.expand_towards_config(closest, random_config)
        new_distance = self.get_config_distance(new_node.config, random_config)

        if new_distance < distance:
            new_node.distance_to_target = self.distance_to_target(new_node.config)
            if self.add_node(new_node):
                return new_node
            else:
                return None
        else:
            return None

    def expand_towards_goal(self, node=None, max_iterations=50):
        if node is None:
            node = self.clostest_to_target
        solver = self.find_path_to_goal(node, max_iterations=max_iterations)
        best = solver.get_best_node()[0]
        solver.board.restore_state(best.state)
        sequence = "".join(BFSMotionPlanner.get_control_sequence(best))
        config = Configuration.from_board(solver.board)
        config.board = self.board
        new_node = RTTNode(config, node, sequence)
        new_node.distance_to_target = self.distance_to_target(new_node.config)
        if new_node.distance_to_target >= node.distance_to_target:
            return None
        if self.add_node(new_node):
            return new_node
        else:
            return None

    def expand_towards_config(self, node, config, max_iterations=40):
        node.config.apply()
        solver = get_motion_planner(
            Instance(self.board, self.target_shape),
            heuristic=self.distance_to_config_heuristic(config),
            precomputed_distances=self._target_distances,
        )
        solution = solver.solve(max_nodes=max_iterations)
        if solution:
            solution_sequence = "".join(solution)
            solution_config = Configuration.from_board(solver.board)
            solution_config.board = self.board
            return RTTNode(solution_config, node, solution_sequence)
        else:
            best = solver.get_best_node()[0]
            solver.board.restore_state(best.state)
            sequence = "".join(BFSMotionPlanner.get_control_sequence(best))
            new_config = Configuration.from_board(solver.board)
            new_config.board = self.board
            return RTTNode(new_config, node, sequence)

    def find_path_to_goal(self, node, max_iterations=500):
        node.config.apply()
        solver = get_motion_planner(
            Instance(self.board, self.target_shape),
            heuristic=GreedyGreatestDistanceHeuristic,
            precomputed_distances=self._target_distances,
        )
        solution = solver.solve(max_nodes=max_iterations)
        if solution:
            solution_sequence = "".join(solution)
            solution_config = Configuration.from_board(solver.board)
            solution_config.board = self.board
            self._solution_node = RTTNode(solution_config, node, solution_sequence)
        return solver

    def expand(self):
        if random.random() <= self.bias:
            new_node = self.expand_towards_goal()
            if new_node is None:
                self.clostest_to_target.feasible = False
        else:
            new_node = self.expand_random()
        if not new_node:
            return

        if new_node.distance_to_target <= 7:
            # if new node is close enough, try to find a direct path to the target
            n = self.expand_towards_goal(node=new_node, max_iterations=500)
            if n is None:
                new_node.feasible = False

    def find_closest_node(self, config):
        min_distance = float("inf")
        selected_node = None
        for node in self.nodes:
            distance = self.get_config_distance(
                node.config, config
            )  # , max_bottleneck=min_distance)
            if distance < min_distance:
                min_distance = distance
                selected_node = node
        return selected_node, min_distance

    def polyominoes_match(self, config1, config2):
        config1.apply()
        poly1 = copy(self.board.polyominoes)
        config2.apply()
        poly2 = self.board.polyominoes
        for p1 in poly1:
            if p1.size == 1:
                continue
            if not any(is_sub_polyomino(p1, p2) for p2 in poly2):
                return False
        return True

    def get_config_distance(self, config1, config2, max_bottleneck=float("inf")):
        if not self.polyominoes_match(config1, config2):
            return float("inf")
        return self.distance_metric(
            config1,
            config2,
            max_bottleneck=max_bottleneck,
            distance_func=lambda x, y: DISTANCES[x][y],
        )

    def distance_to_config_heuristic(self, config):
        class DistanceToConfigHeuristic:
            def __init__(s, motion_planner):
                s._mp = motion_planner
                s._board = s._mp.board
                s._target_shape = s._mp.target_shape

            def __call__(s, score):
                current_config = Configuration.from_board(s._board)
                current_config.board = self.board
                d = self.get_config_distance(current_config, config)
                return d

        return DistanceToConfigHeuristic

    def distance_to_target(self, config, max_distance=float("inf")):
        # sorted list of tuples that contain all tiles and their corresponding distances to the target
        sorted_tiles = list(
            sorted(
                (
                    (self._target_distances[position], tile)
                    for position, tile in config.tiles.items()
                ),
                key=lambda x: x[0],
            )
        )
        # we need at least as many tiles as the target shape contains
        start_index = self.target_shape.size
        for i in range(start_index, len(sorted_tiles) + 1):
            distance, _ = sorted_tiles[i - 1]
            if distance > max_distance:
                return float("inf")
            tiles = [t for _, t in sorted_tiles[:i]]
            if get_blueprint_with_glue_types(
                self._target_shape_positions, tiles, glue_rules=self.board.glue_rules
            ):
                return distance
        return float("inf")

    def extract_solution(self):
        if not self._solution_node:
            return None
        n = self._solution_node
        sequence = ""
        while n.parent:
            sequence = n.sequence + sequence
            n = n.parent
        return sequence

    def _get_stop_condition(self):
        if self.max_nodes is None:

            def stop():
                return self._solution_node or self._stopped

        else:

            def stop():
                return (
                    self._solution_node
                    or self._stopped
                    or len(self.nodes) >= self.max_nodes
                )

        return stop

    def is_finished(self):
        for polyomino in self.board.polyominoes:
            if (
                polyomino.shape_equals(self.target_shape)
                and polyomino.position in self._target_shape_positions
            ):
                return True
        return False

    def solve(self):
        self._stopped = False
        stop_condition = self._get_stop_condition()
        if len(self.nodes) == 1 and self.is_finished():
            self._solution_node = self.nodes[0]
            return self.extract_solution()
        while not stop_condition():
            self.expand()
        return self.extract_solution()


def is_sub_polyomino(p1: Polyomino, p2: Polyomino):
    if p1.size > p2.size:
        return False
    tile_positions1 = p1.tiles
    tile_positions2 = p2.tiles
    for x, y in tile_positions1.keys():
        if _fits_at(tile_positions1, tile_positions2, x, y):
            return True
    return False


def _fits_at(tile_positions1, tile_positions2, x, y):
    for i, j in tile_positions1.keys():
        if not (x + i, y + j) in tile_positions2:
            return False
        if tile_positions2[(x + i, y + j)].glues != tile_positions1[(i, j)].glues:
            return False
    return True


def construct_taxicab_distance_graph(config1, config2):
    g = nx.Graph()
    top_nodes = [(p, 1) for p in config1.tiles.keys()]
    bottom_nodes = [(p, 2) for p in config2.tiles.keys()]
    g.add_nodes_from(top_nodes, bipartite=0)
    g.add_nodes_from(bottom_nodes, bipartite=1)

    for (p1, t1), (p2, t2) in itertools.product(
        config1.tiles.items(), config2.tiles.items()
    ):
        if t1.glues == t2.glues:
            weight = taxicab_distance(p1, p2)
            g.add_edge((p1, 1), (p2, 2), weight=weight)

    return g, top_nodes


def construct_real_distance_graph(config1, config2):
    def real_distance(x, y):
        return DISTANCES[x][y]

    g = nx.Graph()
    top_nodes = [(p, 1) for p in config1.tiles.keys()]
    bottom_nodes = [(p, 2) for p in config2.tiles.keys()]
    g.add_nodes_from(top_nodes, bipartite=0)
    g.add_nodes_from(bottom_nodes, bipartite=1)

    for (p1, t1), (p2, t2) in itertools.product(
        config1.tiles.items(), config2.tiles.items()
    ):
        if t1.glues == t2.glues:
            weight = real_distance(p1, p2)
            g.add_edge((p1, 1), (p2, 2), weight=weight)

    return g, top_nodes


if __name__ == "__main__":
    instance = read_instance("Testcases/easyexample.json")
    solver = RRTSolver(instance)
    solution = solver.solve()
    print(solution)
