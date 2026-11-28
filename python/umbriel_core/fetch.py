"""Downloads for the helper (community shaders, cursor themes): only on the user's request, size-capped and with an
overall deadline. Callers check what they got (SHA-256 from a catalogue or a pinned list)."""

import time
import urllib.error
import urllib.request

USER_AGENT = "umbriel-settings"


class FetchError(ValueError):
    """A readable download failure; the helper reports it as is."""


def urlopen(request, timeout):  # tests replace this
    return urllib.request.urlopen(request, timeout=timeout)


def fetch(url, limit, timeout, deadline=None, opener=None):
    """The body of `url`, at most `limit` bytes, read before `deadline` (monotonic; default now + `timeout`):
    urllib's own timeout covers each socket operation only, so a slow trickle could run far past it."""
    deadline = min(deadline or float("inf"), time.monotonic() + timeout)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    chunks, size = [], 0
    try:
        with (opener or urlopen)(request, max(0.1, deadline - time.monotonic())) as response:
            while size <= limit:
                if time.monotonic() > deadline:
                    raise FetchError(f"Could not download {url}: it took too long.")
                chunk = response.read(min(1 << 16, limit + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
    except (urllib.error.URLError, OSError, ValueError) as error:  # incl. HTTPError and socket timeouts
        if isinstance(error, FetchError):
            raise
        reason = getattr(error, "reason", None) or error
        raise FetchError(f"Could not download {url}: {reason}") from None
    if size > limit:
        raise FetchError(f"{url} is larger than expected.")
    return b"".join(chunks)
