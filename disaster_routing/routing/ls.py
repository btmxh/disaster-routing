import logging
from typing import cast, override

from hydra.utils import instantiate

from .routing_algo import InfeasibleRouteError, RoutingAlgorithm, Route
from ..instances.request import Request
from ..instances.instance import Instance
from ..topologies.topology import Topology
from ..conflicts.config import DSASolverConfig, NPMDSASolverConfig
from ..conflicts.conflict_graph import ConflictGraph
from ..conflicts.solver import DSASolver
from .greedy import GreedyRoutingAlgorithm
from .flow import FlowRoutingAlgorithm


log = logging.getLogger(__name__)


class MofiLSRoutingAlgorithm(RoutingAlgorithm):
    base: RoutingAlgorithm
    dsa_solver: DSASolverConfig
    f_max: int

    def __init__(
        self,
        base: RoutingAlgorithm,
        dsa_solver: DSASolverConfig,
        f_max: int = 100,
    ) -> None:
        super().__init__()
        self.base = base
        self.dsa_solver = dsa_solver
        self.f_max = f_max

    @override
    def route_request(self, req: Request, top: Topology, dst: list[int]) -> list[Route]:
        raise NotImplementedError()

    @staticmethod
    def remove_edge_from_instance(inst: Instance, edge: tuple[int, int]) -> Instance:
        inst = inst.copy()
        u, v = edge
        inst.topology.graph.remove_edge(u, v)
        return inst

    def route_instance_single_pass(
        self, inst: Instance, content_placement: dict[int, list[int]]
    ) -> tuple[list[list[Route]], set[tuple[int, int]], int]:
        routes = self.base.route_instance(inst, content_placement)
        flattened_routes = [r for route in routes for r in route]
        conflict_graph = ConflictGraph(inst, routes)
        dsa_solver = cast(DSASolver, instantiate(self.dsa_solver, conflict_graph))
        indices, mofi = dsa_solver.solve()
        requests_with_mofi = {
            i
            for i, (a, b) in enumerate(zip(indices, conflict_graph.num_fses))
            if a + b == mofi
        }
        edges_with_mofi = {
            edge for r in requests_with_mofi for edge in flattened_routes[r].edges()
        }
        return routes, edges_with_mofi, mofi

    @override
    def route_instance(
        self, inst: Instance, content_placement: dict[int, list[int]]
    ) -> list[list[Route]]:
        routes, edges_with_mofi, mofi = self.route_instance_single_pass(
            inst, content_placement
        )
        for iter in range(self.f_max):
            change = False
            for edge in edges_with_mofi:
                ls_inst = MofiLSRoutingAlgorithm.remove_edge_from_instance(inst, edge)
                try:
                    ls_routes, ls_edges_with_mofi, ls_mofi = (
                        self.route_instance_single_pass(ls_inst, content_placement)
                    )
                    if ls_mofi < mofi:
                        routes = ls_routes
                        edges_with_mofi.discard(edge)
                        edges_with_mofi.update(ls_edges_with_mofi)
                        break
                except InfeasibleRouteError:
                    pass
            if not change:
                break

        return routes


class GreedyLSRoutingAlgorithm(MofiLSRoutingAlgorithm):
    def __init__(self) -> None:
        super().__init__(GreedyRoutingAlgorithm(), NPMDSASolverConfig())


class FlowLSRoutingAlgorithm(MofiLSRoutingAlgorithm):
    def __init__(self) -> None:
        super().__init__(FlowRoutingAlgorithm(), NPMDSASolverConfig())
