"""The seam between the decision loop and whatever is actually flying.

`Runtime` owns exactly one backend and drives it as a state machine: a command
is *started* with `begin()`, advances only when `tick()` is called, and is
*finished* when `poll()` stops returning `None`. That shape exists because a
simulated aircraft has to be stepped and a real one has to be watched; both are
expressed here without the runtime knowing which is which.

Two implementations satisfy this contract:

* `WebotsBackend` — drives Webots and closes each command on PID tolerance,
  so `completed` carries measured displacement evidence.
* `TelloBackend` — drives a physical Tello over the SDK, where `completed` can
  mean the SDK acknowledged movement; land additionally needs stable telemetry.
  See `docs/tello-profile.md`.
"""
from typing import Protocol, runtime_checkable

from .protocol import Action, ActionResult, Observation


class BackendError(RuntimeError):
    """A backend failure carrying a stable machine-readable code.

    `code` is the contract; `str(error)` is for humans and may change. Callers
    that need to branch should compare `.code`.
    """

    def __init__(self, code: str, detail: str = ''):
        self.code = code
        self.detail = detail
        super().__init__(f'{code}: {detail}' if detail else code)


@runtime_checkable
class Backend(Protocol):
    """One owner, one tick stream, at most one command in flight at a time."""

    def tick(self) -> None:
        """Advance the vehicle one step and settle any in-flight command.

        Must be cheap and must never block on a decision. A backend that
        cannot reach its vehicle sets `connected` false and keeps the last
        observation rather than raising; `Runtime.check` turns that into a
        `link_down` mission end.
        """

    def observe(self) -> Observation:
        """The most recent frame plus public flight state.

        Never carries simulator truth: no pose, altitude, displacement or
        evaluator data. `received_at` is host-side monotonic time of arrival
        and drives the staleness check in `Runtime.check`.
        """

    def capture(self) -> Observation:
        """Force a fresh exposure and return it.

        Distinct from `observe`, which may return a frame the loop has already
        seen. The returned frame must be complete and unmodified.
        """

    def begin(self, action: Action, identity: str) -> None:
        """Start one command. `identity` is the caller's action id.

        Raises if a command is already in flight. Must not wait for an ACK:
        the Tello backend sends one datagram here and polls replies on ticks.
        """

    def poll(self) -> ActionResult | None:
        """Return the finished result once, then `None` for every later call.

        `None` means "still running". A command whose completion cannot be
        established returns `status='unknown'` — never `'rejected'` — because
        the runtime latches `motion_unknown` on that status and the model is
        forbidden from retrying a command that may have moved the aircraft.
        """

    def keepalive(self) -> bool:
        """Send an idle heartbeat. Return False if it did not go out.

        Only meaningful while airborne, and only while no translation or
        rotation is running: interleaving a zero-velocity command into an
        active movement would curtail it. Return True when there is nothing to
        keep alive.
        """

    def stop_motion(self) -> None:
        """Abandon any in-flight command and make the vehicle hold position.

        Idempotent, and safe to call when nothing is in flight. Used both by
        the interrupted-execution path and by `Runtime.recover`.
        """

    def close(self) -> None:
        """Release the link. Does not land; recovery lands first."""
