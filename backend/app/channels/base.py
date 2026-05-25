"""ChannelAdapter ABC — implement for each messaging channel (Telegram, WhatsApp, Slack)."""
from abc import ABC, abstractmethod


class ChannelAdapter(ABC):
    """Base class for inbound channel adapters that feed messages into workflow runs."""

    @abstractmethod
    async def start(self) -> None:
        """Start listening for inbound messages (polling / webhook)."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the adapter."""
        ...

    @abstractmethod
    async def send(self, recipient: str, text: str) -> None:
        """Send an outbound message to a recipient."""
        ...

    @abstractmethod
    async def on_message(self, sender: str, text: str, raw: dict) -> None:
        """Called for each inbound message; triggers a workflow run."""
        ...
