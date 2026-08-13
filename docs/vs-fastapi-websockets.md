# Two ways to keep a socket open in Python

[`websocket-presence-board`](https://github.com/i-safonoff/websocket-presence-board)
builds a WebSocket room on FastAPI and raw ASGI: connection tracking, a
Redis pub/sub bridge, backpressure, heartbeats, resume-after-reconnect --
all written by hand. This project builds a much smaller room -- one group
per album, one message type -- on Django Channels, which gives most of
that machinery away for free. The comparison worth making isn't "which
is better," it's "what did the free version actually cost."

## What Channels gives you that the FastAPI project built by hand

**Groups.** `channel_layer.group_add(group_name, channel_name)` /
`group_send(group_name, event)` is the entire pub/sub layer this project
needed. `websocket-presence-board` built the equivalent -- rooms,
membership, cross-instance fan-out -- itself in
[`hub.py` and `bridge.py`](../../websocket-presence-board/src/board/).
Fewer lines here, and also fewer decisions: this project never had to
choose a Redis message shape, a reconnect protocol for the bridge
itself, or what happens to a group's membership when a process restarts.
Channels made all three choices already.

**A dev-time in-memory channel layer.** Channels ships one; swapping it
for `channels_redis.core.RedisChannelLayer` for anything beyond a single
process is a config change, not new code.

## What it costs

**No backpressure story at all.** `websocket-presence-board`'s
`writer.py` exists because uvicorn buffers an unbounded amount of data
for a slow client with no error and no warning -- discovered by finding
that "open a client and never call `recv()`" isn't actually a slow
client (every library reads continuously into its own buffer) and that a
*genuinely* stalled peer has to be a raw socket that finishes the
handshake by hand. Channels' `AsyncWebsocketConsumer.send()` has the
identical exposure -- nothing in this project's `AlbumConsumer` bounds
what happens if a viewer's connection stalls mid-broadcast -- and
Channels gives you no primitive for it. A production version of this
project would need the same bounded-queue-and-evict design
`websocket-presence-board` already built, not a Channels equivalent,
because there isn't one.

**A failure mode the FastAPI project's bridge was built to avoid.**
`websocket-presence-board`'s Redis bridge is fire-and-forget by design --
a subscriber disconnected at the exact moment of a publish misses the
message, and that's an accepted, documented cost, but the bridge itself
never *crashes* a request over it. `channels_redis.core.RedisChannelLayer`
does: `group_send` raises a bare `ConnectionError` when Redis is down,
uncaught by anything Channels provides, and it took actually stopping
the Redis container mid-request to find that this project's first
version let that propagate into a 500 on a write that had already
succeeded (`docs/DECISIONS.md`, decision 3). The FastAPI project's
hand-rolled bridge doesn't have this specific failure mode because it
was written by someone who had already decided fire-and-forget meant
*the publish call itself* couldn't fail loudly. Channels' abstraction
hid that decision instead of making it, which meant this project had to
re-discover and re-make it explicitly.

**No heartbeat, no resume.** Both are still missing here, and for a
different reason than in the FastAPI project: `websocket-presence-board`
built a heartbeat because the browser cannot send or observe WebSocket
ping/pong frames at all (RFC 6455 has them; the JavaScript `WebSocket`
API exposes neither), and a resume buffer because a reconnecting client
needs to know what it missed. Both problems are exactly as real here --
Channels changes nothing about what a browser can or can't do with a raw
socket -- they're just out of scope for what this project set out to
measure, which was S3 and imgproxy, not connection liveness a second
time.

## The actual trade-off

Channels is faster to a working room and slower to a *correct* one under
failure, because the framework's abstractions hide exactly the decisions
(what happens when the pub/sub layer itself is unavailable, what happens
to a slow consumer) that `websocket-presence-board` had to make visible
by not having a framework to hide behind. Building the FastAPI version
first and this one second made that difference legible in a way building
either alone would not have.
