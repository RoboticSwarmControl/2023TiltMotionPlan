import argparse
import cProfile

import threading
from pprint import pprint
from pstats import SortKey, Stats
import io

from tiltmp.core.serialization import read_instance, InstanceEncoder
from tiltmp.mp.motionplanner import *
from tiltmp.mp.rrtmotionplanner import RRTSolver
from tiltmp.mp.solution_data import SolutionData

MEMORY_PROFILING = True
try:
    import resource
except ModuleNotFoundError:
    MEMORY_PROFILING = False
    print("Resource module not found. Memory profiling disabled.")


__all__ = ["profile"]


class StoppableMotionPlannerThread(threading.Thread):
    def __init__(self, motion_planner: MotionPlanner):
        super(StoppableMotionPlannerThread, self).__init__()
        self.motion_planner = motion_planner
        self.stopped = False
        self.solution = None
        self.solved_event = threading.Event()

    def run(self):
        self.solution = self.motion_planner.solve()
        if not self.motion_planner._stopped:
            self.solved_event.set()

    def stop(self):
        self.stopped = True
        self.motion_planner.stop()


def get_solver(name, heuristic, instance):
    if name == "bfs":
        return BFSMotionPlanner(instance)
    if name == "default":
        h = HEURISTICS[heuristic]
        return get_motion_planner(instance, heuristic=h)
    elif name == "tileatatime":
        h = SINGLE_TILE_HEURISTICS[heuristic]
        return OneTileAtATimeMotionPlanner(instance, single_tile_heuristic=h)
    elif name == "rrt":
        return RRTSolver(instance)
    else:
        raise ValueError("Illegal solver configuration")


def main():
    parser = argparse.ArgumentParser(
        description="Solve instance of polyomino construction problem"
    )
    parser.add_argument(
        "input", metavar="IN", type=str, help="file path to an instance or directory"
    )
    parser.add_argument(
        "--out",
        "-o",
        type=str,
        metavar="OUT",
        default=None,
        help="output file path for the profiling results",
    )
    parser.add_argument(
        "--outdir",
        type=str,
        metavar="OUT",
        default=None,
        help="output directory path for the profiling results",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        metavar="T",
        type=int,
        default=None,
        help="maximum time for each instance (default: None)",
    )
    parser.add_argument(
        "--profile",
        "-p",
        action="store_true",
        help="measure time spend in each function (increases runtime)",
    )
    parser.add_argument(
        "--solver",
        "-s",
        type=str,
        metavar="SOLVER",
        default="default",
        help="Solver to be used",
    )
    parser.add_argument(
        "--heuristic",
        type=str,
        metavar="SOLVER",
        default="Weighted Sum of Distances",
        help="Heuristic to be used",
    )

    args = parser.parse_args()

    if args.out is None and args.outdir is None:
        args.out = os.path.join(
            "results",
            os.path.splitext(os.path.basename(args.input))[0] + "_results.json",
        )

    if not args.out and args.outdir and not os.path.isdir(args.outdir):
        try:
            os.mkdir(args.outdir)
        except Exception:
            print("Failed to create output directory")
            exit(-1)

    if os.path.isdir(args.input):
        if not args.outdir:
            print("Input directory requires outdir argument")
            exit(-1)
        filenames = next(os.walk(args.input), (None, None, []))[2]
        filenames = [os.path.join(args.input, f) for f in filenames]
        run_multiple_experiments(
            filenames, args.outdir, args.solver, args.heuristic, timeout=args.timeout
        )
        return

    # single experiment
    if args.out:
        output_file = find_output_file(args.out)
    elif args.outdir:
        output_file = os.path.join(
            args.outdir,
            os.path.splitext(os.path.basename(args.input))[0] + "_result.json",
        )

    try:
        run_experiment(
            args.input,
            output_file,
            args.solver,
            args.heuristic,
            timeout=args.timeout,
            p=args.profile,
        )
    except FileNotFoundError:
        print("Input file not found")
        exit(-1)


def run_experiment(input_file, output_file, solver, heuristic, timeout=None, p=False):
    if os.path.isfile(output_file):
        exit(2)
    instance = read_instance(input_file)
    results = (
        profile(instance, solver, heuristic, timeout=timeout)
        if p
        else measure_time(instance, solver, heuristic, timeout=timeout)
    )
    pprint({k: v for k, v in results.__dict__.items() if k != "runtime_profile"})
    if MEMORY_PROFILING:
        max_mem_usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        results.max_mem_usage = max_mem_usage
    write_results_file(results, output_file)
    if results.timed_out:
        exit(1)


def run_multiple_experiments(
    input_files, output_folder, solver, heuristic, timeout=None
):
    for file in input_files:
        print(file)
        output_file = os.path.join(
            output_folder, os.path.splitext(os.path.basename(file))[0] + "_result.json"
        )
        try:
            run_experiment(file, output_file, solver, heuristic, timeout=timeout)
        except:
            break


# finds unique path for output file
def find_output_file(path: str):
    if not os.path.exists(path):
        return path
    split = path.rsplit(".", 1)
    if len(split) == 1:
        prefix, suffix = split[0], ""
    else:
        prefix, suffix = split
    i = 1
    while os.path.exists(prefix + str(i) + "." + suffix):
        i += 1
    return prefix + str(i) + "." + suffix


def write_results_file(results: SolutionData, output_file: str):
    data = {k: v for k, v in results.__dict__.items() if k != "instance"}
    if "instance" in results.__dict__:
        data["instance"] = InstanceEncoder.encode_instance(results.__dict__["instance"])
    with open(output_file, "w") as f:
        json.dump(data, f, indent=4)


def extract_stats(pr: cProfile.Profile, sort_by=SortKey.CUMULATIVE):
    s = io.StringIO()
    ps = Stats(pr, stream=s).strip_dirs().sort_stats(sort_by)
    ps.print_stats()
    return s.getvalue()


class SolverTimeoutException(Exception):
    def __init__(self, solver):
        super().__init__()
        self.solver = solver


def _solve(instance: Instance, solver_name, heuristics, timeout=None):
    try:
        solver = get_solver(solver_name, heuristics, instance)
    except TimeoutError:
        # return dummy motion planner without expanded nodes
        raise SolverTimeoutException(BFSMotionPlanner(instance))
    if timeout:
        thread = StoppableMotionPlannerThread(solver)
        thread.start()
        if not thread.solved_event.wait(timeout):
            thread.stop()
            thread.join()
            raise SolverTimeoutException(solver)
    else:
        solver.solve()
    return solver


def measure_time(instance: Instance, solver_name, heuristics, timeout=None):
    timed_out = False
    t0 = time.time()
    try:
        solver = _solve(instance, solver_name, heuristics, timeout)
    except SolverTimeoutException as e:
        timed_out = True
        solver = e.solver
    solution = solver.extract_solution()
    time_needed = time.time() - t0

    if solution is None:
        solution = None
    else:
        solution = "".join(solution)

    try:
        nn = solver.number_of_nodes
    except AttributeError:
        nn = 0
    data = SolutionData(solution, time_needed, instance=instance, number_of_nodes=nn)
    data.timed_out = timed_out
    return data


def profile(instance: Instance, solver_name, heuristics, timeout=None):
    timed_out = False
    t0 = time.time()
    pr = cProfile.Profile()
    pr.enable()
    try:
        solver = _solve(instance, solver_name, heuristics, timeout=timeout)
    except SolverTimeoutException as e:
        timed_out = True
        solver = e.solver
    solution = solver.extract_solution()
    pr.disable()

    if solution is None:
        solution = None
    else:
        solution = "".join(solution)

    pr.print_stats(sort=SortKey.CUMULATIVE)
    stats = extract_stats(pr)
    time_needed = time.time() - t0
    try:
        nn = solver.number_of_nodes
    except AttributeError:
        nn = 0
    data = SolutionData(
        solution,
        time_needed,
        runtime_profile=stats,
        instance=instance,
        number_of_nodes=nn,
    )
    data.timed_out = timed_out
    return data


if __name__ == "__main__":
    main()
