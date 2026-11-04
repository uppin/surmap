"""A slow station never stalls the page's stream: the bridge keeps reading while it works and
works on the newest pair (`bevy_bridge.serve_connection`)."""

import asyncio
import threading
from collections.abc import AsyncIterator, Sequence

from surmap.simulation.bevy_bridge import serve_connection
from surmap.simulation.bevy_wire import BevyPair, BridgeStatus, decode_bevy_message
from tests.fleet_perception_fakes import a_hello, a_pair

# How long the station holds its first pair at most; the page releases it well before.
HOLD_S = 2.0


class SlowStation:
    """A session that holds the first pair it is handed until the page releases it, and records
    what it handled: `hello` or `pair <frame_id>`."""

    def __init__(self) -> None:
        self.handled: list[str] = []
        self.holding = threading.Event()
        self.release = threading.Event()

    def handle(self, message: bytes) -> BridgeStatus:
        decoded = decode_bevy_message(message)
        if isinstance(decoded, BevyPair):
            if not self.holding.is_set():
                self.holding.set()
                self.release.wait(HOLD_S)
            self.handled.append(f"pair {decoded.frame_id}")
        else:
            self.handled.append("hello")
        return BridgeStatus(frames=len(self.handled), posed=0, lost=False, keyframes=0, dropped=0)


async def a_page(
    station: SlowStation, first: Sequence[bytes], while_held: Sequence[bytes]
) -> AsyncIterator[bytes]:
    """The page's socket: `first`, then — once the station holds a pair — `while_held`; the
    station is released only after the bridge has read all of them."""
    for message in first:
        yield message
    await asyncio.to_thread(station.holding.wait, HOLD_S)
    for message in while_held:
        yield message
    station.release.set()


def stream(station: SlowStation, first: Sequence[bytes], while_held: Sequence[bytes]) -> list[str]:
    """Runs one connection to its end; the status replies the page received."""
    replies: list[str] = []

    async def send(reply: str) -> None:
        replies.append(reply)

    asyncio.run(serve_connection(a_page(station, first, while_held), send, station.handle))
    return replies


def test_a_slow_station_works_on_the_newest_pair_and_skips_the_ones_it_superseded() -> None:
    # Given a station busy with pair 1
    station = SlowStation()

    # When pairs 2, 3 and 4 arrive while it works
    stream(
        station, [a_hello(), a_pair(1, None)], [a_pair(2, None), a_pair(3, None), a_pair(4, None)]
    )

    # Then it goes on with pair 4 and never sees 2 or 3
    assert station.handled == ["hello", "pair 1", "pair 4"]


def test_a_hello_arriving_while_the_station_works_is_never_skipped() -> None:
    # Given a station busy with pair 1
    station = SlowStation()

    # When a pair, a hello and another pair arrive while it works
    stream(station, [a_hello(), a_pair(1, None)], [a_pair(2, None), a_hello(), a_pair(3, None)])

    # Then the hello is handled, and of the pairs only the newest
    assert station.handled == ["hello", "pair 1", "hello", "pair 3"]


def test_every_message_the_station_handles_is_answered() -> None:
    # Given a station busy with pair 1
    station = SlowStation()

    # When pairs 2 and 3 arrive while it works
    replies = stream(station, [a_hello(), a_pair(1, None)], [a_pair(2, None), a_pair(3, None)])

    # Then one status goes back per message it handled
    assert len(replies) == len(station.handled) == 3
