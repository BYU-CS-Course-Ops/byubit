# Bit refactor: use tracecode as the execution ledger

## Goal

Replace Bit's per-operation `history` snapshots as the source of playback truth with a `tracecode.TraceRecorder` recording for each Bit/world run. Keep Bit responsible for supplying serializable world state, enforcing Bit-specific safety/error/comparison semantics, and rendering the result. Do not replace the Bit API or make the trace viewer execute or reverse student code.

Tracecode 0.1.2 is in the sibling `tracecode` project. Its relevant API is `TraceRecorder(serializers=[...], target_file=...)`, used as a context manager around a direct call to the student function. Do **not** use the `tracecode` CLI or `exec_source` for this integration: Bit already has a live `Bit` object, invokes student callables for multiple worlds, and uses its own Bit-specific renderer.

## Recommended recording approach

In the per-world evaluation path (`Bit._evaluate`, or a small helper it delegates to):

1. Determine the student source filename from the student callable (use its code object's filename or `inspect.getfile` carefully if decorators/wrappers are involved). Pass this as `target_file`; tracecode reads the file for source metadata.
2. Construct a fresh recorder for each world/run, registering a serializer for `Bit` before entering it.
3. Invoke the student function with the live `Bit` under `with recorder:`. Keep comparison against the expected world outside that context, as it is a Bit post-run operation, not part of the student's source execution.
4. Retain `recorder.recording` as the execution ledger and associate it with that world's result. The recording starts with one `source` record; subsequent records are snapshots. Keep result ordering stable across worlds.

Illustrative shape (adapt names to the existing call structure):

```python
def serialize_bit(bit):
    return {
        "name": bit.name,
        "world": [list(row) for row in bit.world],
        "pos": [int(value) for value in bit.pos],
        "orientation": int(bit.orientation),
    }

recorder = TraceRecorder(
    serializers=[(Bit, serialize_bit)],
    target_file=student_filename,
    max_snapshots=...,  # choose deliberately; see limits below
)
with recorder:
    bit_function(bit, *args, **kwargs)
```

The serializer must return only detached JSON-native data. The world is mutable, and positions may be NumPy arrays/scalars in existing use, so normalize rows/positions/scalars to lists and built-in strings/integers. Tracecode serializes the returned structure immediately, but do not return references to mutable Bit state or opaque NumPy objects. The encoded Bit value will be tagged, e.g. `{"type":"byubit.bit.Bit","data":{...}}`; the Bit renderer must decode that value rather than assume the serializer's data appears untagged.

Each snapshot's target-frame `locals` and `globals` (and `callers`) can contain serialized Bit values. Usually the student's local named `bit` is the relevant state, but support a module/global binding too. Build a small tested helper to find/decode a Bit state from these structures. Do not make the serializer call `str()` or serialize unrelated Bit internals such as `history`, `state_counts`, or renderer objects.

## Trace semantics that affect the UI

- A `line` snapshot is before that source line executes.
- For a Python Bit method wrapper that returns directly into a student frame, tracecode emits `call_return` at the student's call-site after the wrapper has completed. The Bit serializer therefore captures post-operation world, position, and orientation. The call's explicit return value is in `call_return.value`; mutators commonly return `None`, while predicates/accessors return useful booleans/strings. Caller locals are still pre-assignment at that instant; the next line snapshot captures the assignment/expression result.
- Multiple external Python returns on one source line are ordered, and each gets its own post-return caller snapshot. External-to-external returns do not produce separate events; only a return whose immediate caller is target/student code is recorded.
- Only Python frame returns are visible. C builtins/native calls do not get synthetic return events. `input` has its own prompt/return events. Generator/coroutine suspension is excluded from ordinary return events.
- Exceptions do not produce successful `call_return` events. Tracecode records exceptions in target frames, including a traceback that can mention Bit frames. Bit's `_evaluate` still needs to catch/classify escaping `MoveOutOfBoundsException`, `MoveBlockedByBlackException`, `BitComparisonException`, `BitInfiniteLoopException`, and other errors as before.
- The return event's function name comes from the actual frame code object (`co_name`/`co_qualname`), not a wrapper's `functools.wraps` metadata. Bit's `_registered` decorator wraps methods in a shared `new_func` code body, so initially verify what method names appear in `call_return`. The event still has the student's source line and the serialized Bit state. If the generic wrapper label makes playback unclear, prefer making each `_registered` wrapper's code object carry its public method name (`code.replace(co_name=..., co_qualname=...)`) and test it; this is simpler than adding a tracecode-specific name-resolution API. Do not assume names are already `Bit.move`.
- Tracecode intentionally suppresses its own injected condition helper, stdout tee writes, and wrapped `input` from general `call_return` events. Do not reintroduce these framework-internal events in the Bit renderer.

## Replacing the current custom machinery without losing Bit behavior

The new recording should become the single execution/playback timeline; do not maintain a parallel per-method `history` just to drive navigation. The existing Bit history currently also performs non-rendering work, so separate responsibilities before deleting it:

- `_record`/`_register` currently create detached `BitHistoryRecord`s with action titles, source locations, error text, and annotations; `_register` also updates repeat-state counts and enforces `MAX_REPEAT_STATE` / `MAX_STEP_COUNT`. Remove the history accumulation only after the trace-driven renderer and tests are in place. Preserve the loop/repeat safeguards independently (e.g. a small operation/state counter hook in `_registered`) because line snapshots are not equivalent to one Bit action per count.
- Preserve `Bit._evaluate`'s exception classification and expected-world comparison. An exception escaping student code is visible in the trace, but the classified Bit outcome/message still needs to be attached for the UI. Expected-world comparison occurs after the target function returns and thus is not naturally a student-frame snapshot. Represent comparison success/failure and other final status as a small explicit Bit outcome/final record associated with the trace (or a renderer adapter); do not pretend it came from a target line. Keep expected-world annotations (expected world/position/orientation) available to the renderer.
- Keep `Bit._results` / `get_json_results`, multi-world ordering, `@Bit.worlds`/`@Bit.empty_world` behavior, renderer protocol, and current user-facing error messages compatible unless a separate migration decision says otherwise.
- The existing HTML template expects a per-world list of records with `name`, `line_number`, `world`, `pos`, `orientation`, `error_message`, and optional `annotations`; it uses event names such as `snapshot...` for navigation. Either adapt the renderer/template to consume tracecode events directly, or add one clearly defined view-model adapter from tracecode recordings to Bit display events. Keep the raw tracecode recording canonical and avoid storing both full legacy history and full trace unless needed for a short migration. Update the template's navigation, line highlighting, world panel, error panel, and JSON results together.
- Tracecode also captures target locals/globals, return values, calls, conditions, console deltas, and traceback records. Decide which pieces the Bit UI presents; do not flatten away the raw trace if it is useful for debugging. Its existing bounded serializer/snapshot limits and opaque fallback apply.

## Bounds and failure handling

Tracecode's `max_snapshots` limit raises `RecordingLimitExceeded` and stops tracing; it is not a silent truncation mode. Choose a limit compatible with Bit's existing `MAX_STEP_COUNT` and per-run UI budget. Preserve the existing behavior for long/infinite programs deliberately: a recorder limit should not accidentally be reported as a generic student error or silently produce a misleading successful result. Keep Bit's repeat-state and operation-count protections even if the trace has its own cap. Test that `sys.settrace`, stdout/stdin, and `input` are restored for successful, exceptional, and limit-exceeded runs.

If tracecode is not available in the Bit environment, add it as a runtime dependency at version 0.1.2 or later and update the lockfile. For local development against sibling checkouts, an editable local source may be used temporarily, but do not commit a machine-specific path as the published dependency source.

## Suggested implementation/test sequence

1. Add the tracecode dependency and a Bit serializer; add a focused test that records a student function calling `move`, `paint`, a predicate, and accessor, then verify call-return values and detached Bit state at each return.
2. Prototype a decorated `_registered` method call and inspect the raw `call_return` name/qualified name. Resolve generic wrapper naming if necessary before designing labels around it.
3. Record a student function with several Bit calls on one source line and verify event order; verify the next line snapshot shows assigned values while the return snapshot correctly remains pre-assignment.
4. Integrate one world's raw recording into the Bit renderer, then multi-world runs. Preserve `Bit._results` and JSON API compatibility.
5. Add regressions for caught/uncaught Bit errors, out-of-bounds/blocked moves, wrong and correct expected worlds, loop/repeat safeguards, console input/output, snapshot limits, and detached prior world states. Ensure the final comparison/error status appears even though it happens after target execution.
6. Run the full Bit test suite and demos; inspect generated HTML/JSON for wrapper/helper noise, source line mapping, and playback order before removing the old history path.
