from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseAgent(ABC):
    """
    Base interface for all agents in the AI Affiliate Engine.
    Agents are stateless and deterministic given the same input.
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
        pass
