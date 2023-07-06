class SolutionData:
    def __init__(
        self,
        control_sequence,
        time_needed,
        runtime_profile="",
        instance=None,
        number_of_nodes=0,
    ):
        if instance:
            self.instance = instance
        self.control_sequence = control_sequence
        if control_sequence is not None:
            self.control_sequence_length = len(control_sequence)
        if number_of_nodes:
            self.number_of_nodes = number_of_nodes
        self.time_needed = time_needed
        self.timed_out = False
        if runtime_profile:
            self.runtime_profile = runtime_profile
