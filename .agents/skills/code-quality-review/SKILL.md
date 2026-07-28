---
name: code-quality-review
description: Run a strict maintainability and architecture review for code changes or a codebase. Use when the user wants review findings for structural regressions, overbuilt design, shallow modules, spaghetti branching, file bloat, weak ownership, public contract drift, or a thermonuclear-level quality audit.
metadata:
  uuid: "d5fdc9f9-70b2-4bf4-bae9-1171151fffec"
---

# Code Quality Review

Use this skill for a findings-first review focused on maintainability, architecture, and code health. The bar is higher than "the tests pass": behavior should remain correct while the implementation becomes simpler, deeper, and easier to reason about.

## Vocabulary

Use these terms consistently:

- **Module**: anything with an interface and an implementation.
- **Interface**: everything a caller must know to use a module correctly, including invariants, ordering, error modes, and configuration.
- **Implementation**: the code inside a module.
- **Seam**: where an interface lives; a place behavior can vary without editing callers.
- **Adapter**: a concrete thing satisfying an interface at a seam.
- **Depth**: leverage at the interface. A deep module hides substantial behavior behind a small interface.
- **Leverage**: capability callers get per unit of interface.
- **Locality**: change, bugs, and verification concentrated in one place.

Prefer these terms over "component," "service," "API," or "boundary."

## Source Priority

Use this order when judging a change:

1. Explicit user direction.
2. Repository instructions such as `AGENTS.md`.
3. Architecture docs, specs, ADRs, and design notes.
4. Existing implementation.

Existing code can show conventions, but it does not justify preserving accidental complexity.

## Review Posture

Prioritize findings in this order:

1. Correctness bugs and user-visible regressions.
2. Structural regressions that make the codebase harder to change.
3. Missed simplifications where a smaller design would delete concepts, branches, helpers, or paths.
4. Spaghetti branching, scattered special cases, and unclear ownership.
5. Weak interfaces, shallow modules, unnecessary seams, or adapters that do not buy leverage.
6. Type, data-shape, or contract ambiguity that obscures real invariants.
7. File bloat, decomposition problems, and readability issues.

Do not flood the review with cosmetic nits when larger structural issues exist.

## Strict Quality Checks

Flag aggressively when a change:

- adds ad-hoc branches to an already busy implementation
- creates duplicate public/private, GUI/non-GUI, helper/command, or feature-specific execution paths
- puts domain behavior in the wrong owner or layer
- adds a new seam with only one adapter
- introduces wrappers, managers, helpers, flags, or state that do not improve leverage or locality
- relies on `any`, `unknown`, casts, optionality, or loose object shapes to hide an unclear interface
- duplicates existing helpers or ignores a canonical module
- pushes a file past a maintainability threshold, especially around 1000 lines, without a strong reason
- adds speculative fallback behavior, compatibility shims, migration paths, or policy not required by the task
- serializes independent work or makes related updates non-atomic when the simpler structure is obvious
- preserves incidental complexity when there is a visible "code judo" move that deletes it

## Authoritative Path Checks

When the project documents a command path, public interface, view/domain split, or execution owner, treat that as reviewable architecture:

- User actions should remain reproducible through the documented public command or interface when that is the contract.
- View or UI modules should not become owners of domain execution or authoritative state.
- Translation modules should translate representation, not become hidden implementation paths.
- A new feature kind should extend an existing mechanism before creating a parallel registry, store, or protocol path.

Raise these as real findings even if the code appears functionally correct.

## Tests

Review tests with the same rigor as application code.

Prefer tests that:

- assert public behavior through the intended interface
- prove architecture contracts when those contracts matter
- stay concise after implementation simplification
- survive internal refactors

Flag tests that pin helper names, call order, private state, CSS/DOM structure, workaround behavior, or temporary plumbing.

## Output

Present findings first, ordered by severity, with file and line references where possible. For each finding, explain the risk and the smallest concrete remediation. If no issues are found, say that clearly and mention residual testing or review risk.

If the user asks for a thermonuclear review, raise the strictness bar: treat avoidable complexity, file bloat, spaghetti growth, and missed structural simplification as presumptive blockers.
