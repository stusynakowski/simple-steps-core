# Rules for simple-steps-core

Carried over from Simple Steps (docs/core-proposals/011-core-handover.md).

- The grid is the only model. Anything that isn't the grid model is moved
  onto it or removed.
- Verify a claim by running it, never by reading docs.
- No mutable state at module level: everything a workflow uses hangs off its
  kernel (K24).
- An empty step is a 1x1 frame with one cell "empty", never a placeholder.
- Extras live under a namespace and are never hashed (K21).
- Each behaviour change is confirmed in small pieces.
