"""Registro de agentes: el directorio oficial del ecosistema.

Solo los agentes registrados pueden recibir tareas. El registro indexa
por capacidad para que el orquestador encuentre al agente adecuado.
"""

from __future__ import annotations

from governed_agents.core.agent import Agent


class AgentAlreadyRegistered(Exception):
    pass


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        if agent.agent_id in self._agents:
            raise AgentAlreadyRegistered(agent.agent_id)
        self._agents[agent.agent_id] = agent

    def unregister(self, agent_id: str) -> None:
        self._agents.pop(agent_id, None)

    def get(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def find_by_capability(self, capability: str) -> list[Agent]:
        return [
            agent
            for agent in self._agents.values()
            if agent.identity.has_capability(capability)
        ]

    def all(self) -> list[Agent]:
        return list(self._agents.values())
