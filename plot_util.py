import os
from collections import defaultdict
from copy import deepcopy

import numpy as np
import json

from tiltmp.core.serialization import read_instance, decode_instance
from tiltmp.mp.solution_data import SolutionData


def get_additional_instances(path, regex, solved_names, fixed_only=False):
    """Load instances from the directory path that match regex and are not in solved_names. These instances are counted as timed_out.
    :param fixed_only: Iff this is True, only instances that contain "fixed" in their filename are loaded.
    """
    instances = []
    for filename in os.listdir(path):
        if not regex.match(filename) or not filename.endswith(".json"):
            continue
        if filename.rsplit(".", 1)[0] in solved_names:
            continue
        if fixed_only and "notfixed" in filename:
            continue
        i = read_instance(os.path.join(path, filename))
        s = SolutionData("", 1, instance=i)
        if "maze" in filename:
            s.board_type = "maze"
        elif "cave" in filename:
            s.board_type = "cave"
        s.file_name = filename.rsplit(".", 1)[0] + "_result.json"
        s.timed_out = True
        instances += [s]
    return instances


def load_file(file):
    with open(file) as f:
        data = json.load(f)
    for required in ["control_sequence", "time_needed"]:
        if required not in data:
            return None
    if "instance" in data:
        data["instance"] = decode_instance(data["instance"])
    solution = SolutionData("", 0)
    for key, value in data.items():
        try:
            setattr(solution, key, value)
        except AttributeError:
            pass
    return solution


def number_of_nodes(solution_data: SolutionData):
    try:
        return solution_data.number_of_nodes
    except AttributeError:
        return 0


def time_needed(solution_data: SolutionData):
    if solution_data.timed_out:
        return float("inf")
    return solution_data.time_needed


def target_shape_size(solution_data: SolutionData):
    return solution_data.instance.target_shape.size


def number_of_tiles(solution_data: SolutionData):
    return len(solution_data.instance.initial_state.get_tiles())


def board_size(solution_data: SolutionData):
    return np.prod(solution_data.instance.initial_state.concrete.size)


def solution_length(solution_data: SolutionData):
    if solution_data.control_sequence is None:
        return float("inf")
    return solution_data.control_sequence_length


def glue_types(solution_data: SolutionData):
    return len(solution_data.instance.initial_state.glue_rules.get_glues())


def is_fixed(solution_data: SolutionData):
    return hasattr(solution_data.instance.initial_state, "fixed_tiles")


def memory_usage(solution_data: SolutionData):
    return solution_data.max_mem_usage / 1000000


def evaluate_solution_length_difference(data1, data2, compare_by=board_size):
    ratios = defaultdict(list)
    for instance in data1:
        instance2 = [i for i in data2 if i.file_name == instance.file_name][0]
        if instance.control_sequence_length and instance2.control_sequence_length:
            ratios[compare_by(instance)].append(
                instance2.control_sequence_length / instance.control_sequence_length
            )
    for size, r in ratios.items():
        print(size, "average:", sum(r) / len(r))
        print("standard deviation", np.std(r, ddof=1))
        se = np.std(r, ddof=1) / np.sqrt(np.size(r))
        print("+/-", se)
    all = sum(ratios.values(), [])
    print("total", "average:", sum(all) / len(all))


def steps_to_goal(solution_data: SolutionData):
    board = solution_data.instance.initial_state
    target_shape = solution_data.instance.target_shape
    if len(board.get_tiles()) != target_shape.size:
        return None
    if hasattr(board, "fixed_tiles"):
        return None
    if solution_data.timed_out or solution_data.control_sequence is None:
        return None
    board = deepcopy(board)
    tile = next(iter(board.get_tiles()))
    i = 0
    while tile.parent.size != target_shape.size:
        board.step(solution_data.control_sequence[i])
        board.activate_glues()
        i += 1
    return len(solution_data.control_sequence) - i


def get_complementary(color):
    r, g, b = color
    r_comp = max(r, b, g) + min(r, b, g) - r
    g_comp = max(r, b, g) + min(r, b, g) - g
    b_comp = max(r, b, g) + min(r, b, g) - b
    return (r_comp, g_comp, b_comp)


AXIS_FUNCTIONS = {
    "nodes": number_of_nodes,
    "time": time_needed,
    "tiles": number_of_tiles,
    "size": board_size,
    "solution_length": solution_length,
    "glues": glue_types,
    "target_size": target_shape_size,
    "mem": memory_usage,
}

AXIS_LABELS = {
    "nodes": "number of nodes",
    "time": "time [s]",
    "tiles": "number of tiles",
    "size": "board size",
    "solution_length": "solution length",
    "glues": "glue types",
    "target_size": "target shape size",
    "mem": "peak memory usage [GB]",
}
