from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseAgent(ABC):
    """
    Base interface for all agents in the AI Affiliate Engine.

    Agents should be stateless.
    If an agent uses an LLM, keep runs *mostly* reproducible by using:
      - temperature near 0
      - a fixed seed
    """

    name: str

    @abstractmethod
    def run(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the agent.

        Args:
            input: Structured input dictionary defined by the agent schema.

        Returns:
            Structured output dictionary defined by the agent schema.
        """
        raise NotImplementedError
