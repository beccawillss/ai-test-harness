---
name: write-adr
description: Write an Architecture Decision Record for a design decision
  made in this project. Use after any significant design discussion or
  when the user invokes /write-adr.
---

# Writing an ADR

Create a new file in `docs/adr/` named `NNNN-short-slug.md` (NNNN =
next number in sequence, zero-padded). One page maximum. Write in plain
prose — no bullet-point walls, no marketing tone. The reader is a
future engineer (or interviewer) asking "why is it built this way?"

Use this template:

    # NNNN. <Decision as a short imperative title>

    Date: YYYY-MM-DD
    Status: Accepted

    ## Context
    What situation forced a decision? What constraints and forces were
    in play (cost, nondeterminism, portfolio goals, tooling limits)?
    2-4 sentences. State the problem, not the solution.

    ## Decision
    What we chose, stated plainly in one or two sentences, then a short
    paragraph on how it works in this codebase (name real modules).

    ## Alternatives considered
    The 1-3 realistic alternatives and the specific reason each lost.
    Be honest about what the rejected options did better.

    ## Consequences
    What gets easier, what gets harder, what we're now committed to.
    Include at least one genuine downside — an ADR with no cost listed
    is advertising, not a record.

Rules:
- Record decisions that were actually made, not aspirations.
- If the decision reverses an earlier ADR, set that ADR's status to
  "Superseded by NNNN" — don't edit its content.
- Ask the user for the decision's reasoning if it isn't in the
  conversation; don't invent rationale.