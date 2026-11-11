'''
Trusted Time Source for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-11-11
'''
# The time t of the decision rule is read from a source the server does not control (thesis Section 6.2.5):
# the timestamp of the latest block, obtained through a provider that the caller injects. The system clock is
# only a fallback, and the label that is returned with the time says which of the two was used, so that the
# audit ledger shows every decision that relied on the server clock. The block number is returned with the
# time, so that an auditor can compare the time of a recorded decision with the chain.
from datetime import datetime

SOURCE_BLOCK = "block-timestamp"
SOURCE_SYSTEM = "system-clock-fallback"


class TimeSourceError(RuntimeError):
    """The trusted source gave no usable time and the fallback to the system clock was not allowed."""


def block_provider(w3):
    """Provider for a web3 connection: returns the latest block, which carries `timestamp` and `number`."""
    def latest_block():
        return w3.eth.get_block("latest")
    return latest_block


def _field(value, name):
    if isinstance(value, dict):
        return value.get(name)
    try:
        return value[name]                     # a web3 block answers to block["timestamp"]
    except Exception:
        return getattr(value, name, None)


def _from_provider(provider):
    """Read the provider once. Returns (time, unix seconds, block number) or raises ValueError."""
    value = provider()
    if isinstance(value, datetime):
        moment = value.astimezone().replace(tzinfo=None) if value.tzinfo is not None else value
        return moment, int(moment.timestamp()), None
    number = None
    if not isinstance(value, (int, float)):
        value, number = _field(value, "timestamp"), _field(value, "number")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
        raise ValueError("the provider returned no timestamp")
    # Unix seconds become a local time without a zone, the form in which the consent window is stored
    return datetime.fromtimestamp(int(value)), int(value), number


def read_time(provider=None, allow_fallback=True, system_clock=None, max_lag_seconds=None):
    """The time for a decision with its evidence: time, source, unix, block_number, reason (why the fallback was
    used) and clock_skew_seconds (trusted time minus the system clock, None on the fallback).
    provider: a callable without arguments that returns the latest block (a mapping or object with `timestamp`),
    Unix seconds, or a datetime. A provider for another source, such as a stated beacon, names it in an attribute
    `source`. system_clock: a callable that returns the local time, datetime.now by default.
    allow_fallback=False raises TimeSourceError instead of using the system clock.
    max_lag_seconds: when given, a trusted time that is more than this many seconds behind the system clock is
    treated as a failed read (a node that has stopped following the chain would keep an expired consent in its
    window). None applies no limit. The latest block is normally up to one block interval behind."""
    clock = system_clock or datetime.now
    reason = "no provider configured"
    if provider is not None:
        try:
            moment, unix, number = _from_provider(provider)
            skew = (moment - clock()).total_seconds()
            if max_lag_seconds is not None and -skew > max_lag_seconds:
                raise ValueError(f"the trusted time is {int(-skew)} seconds behind the system clock")
            return {"time": moment, "source": getattr(provider, "source", SOURCE_BLOCK), "unix": unix,
                    "block_number": number, "reason": None, "clock_skew_seconds": skew}
        except Exception as error:
            reason = f"provider failed: {error}"[:200]
    if not allow_fallback:
        raise TimeSourceError(reason)
    moment = clock()
    return {"time": moment, "source": SOURCE_SYSTEM, "unix": int(moment.timestamp()), "block_number": None,
            "reason": reason, "clock_skew_seconds": None}


def trusted_now(provider=None, allow_fallback=True, system_clock=None, max_lag_seconds=None):
    """The time and the label of its source, as a pair: the block time with the label "block-timestamp" when the
    provider answered, and the system clock with the label "system-clock-fallback" when there is no provider or it
    failed. The time can be passed as `now` to evaluate_allow, lifecycle_state and validate_lifecycle."""
    t = read_time(provider, allow_fallback=allow_fallback, system_clock=system_clock, max_lag_seconds=max_lag_seconds)
    return t["time"], t["source"]
