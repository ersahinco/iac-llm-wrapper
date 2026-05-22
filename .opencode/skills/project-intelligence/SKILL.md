---
name: project-intelligence
description: Use when starting any session, implementing features, or making architectural changes. Enforces standards, manages knowledge transfer between sessions, tracks implementation progress, and ensures reliable collaborative development. Auto-applies to all work.
---

# Project Intelligence

Enforce standards, maintain living documentation, and ensure reliable knowledge transfer between sessions. This skill applies to ALL work — not optional.

## Session Lifecycle

### Start of Session
1. Read `AGENTS.md` → `## Session State` section
2. Confirm current goal, check blockers, verify test/lint status
3. If Session State missing or stale, ask user to clarify before proceeding
4. Load any referenced files mentioned in Current Goal

### During Work
1. Update `## Session State` → `Done` checkboxes as items complete
2. Log key decisions immediately when made (don't wait until end)
3. If blocked, update `## Session State` → `Blockers` section
4. If scope changes, update `Current Goal` and add to `Key Decisions`

### Before Commit
1. Run quality gates (tests + lint + format)
2. Update `## Session State` → `Status` with current test count and lint status
3. Write `Key Decisions This Session` with rationale
4. If tests fail or lint dirty, DO NOT commit — fix first

### End of Session
1. Update `Current Goal` to next item from `Next` list
2. Verify all `Done` items are actually complete
3. Flag any new blockers or risks
4. Ensure `AGENTS.md` is committed with code changes

## Standards Enforcement

### Code Standards
- **Type safety**: Pydantic v2 models for all data structures. No `dict` for domain objects.
- **Error handling**: Fail-closed validation. Raise specific exceptions with context. Never swallow errors.
- **Testing**: Every feature has tests. 167+ tests passing. No commit without tests.
- **Linting**: ruff clean, format check passes. No exceptions.
- **Naming**: Ubiquitous language — "decision", "requirement", "pattern", "catalog", "intent". No conflicting terms.

### Architecture Standards
- **Model-driven**: Requirement graph is the product. New features = new `Requirement` node. Don't modify extraction/interview/generation core code.
- **Pattern-driven**: Patterns carry their own graph factories, catalogs, validators. New patterns register without core changes.
- **Context-gated defaults**: Defaults only apply when conditions are met. No flat defaults.
- **No IaC generation**: Tool produces decision artifacts, not deployable CDK/Terraform/CloudFormation.

### Documentation Standards
- **Honest positioning**: No "deterministic" claims. No "compiler" claims. Value is structure + traceability.
- **Stakeholder-focused**: Every feature should answer "what does this give the architect/engineer/compliance?"
- **Living docs**: AGENTS.md and README.md updated with every significant change.
- **Caveman principles**: Lean, ubiquitous language, clear goal, don't reinvent wheel.

## Knowledge Transfer Protocol

### What Gets Tracked
| Artifact | Location | Purpose |
|----------|----------|---------|
| Current goal | `AGENTS.md` → `## Session State` → `Current Goal` | What we're building now |
| Progress | `AGENTS.md` → `## Session State` → `Done` / `Next` | What's done, what's next |
| Decisions | `AGENTS.md` → `## Session State` → `Key Decisions` | Why we chose X over Y |
| Blockers | `AGENTS.md` → `## Session State` → `Blockers` | What's stopping progress |
| Architecture | `AGENTS.md` → `## Architecture` | How the system works |
| Standards | This skill file | What rules to enforce |

### Confidence Scoring
When making changes, flag confidence level:
- **High**: Tests pass, follows established patterns, clear requirements
- **Medium**: Tests pass, but novel approach or unclear requirements
- **Low**: Tests pass, but significant architectural change or uncertain impact

If confidence is Low, explicitly state risks and ask user to confirm before proceeding.

### Decision Logging Format
```
Decision: <what was decided>
Context: <why this matters>
Alternatives: <what was considered and rejected>
Confidence: <High/Medium/Low>
```

## Quality Gates

### Pre-Commit Checklist
- [ ] All tests pass (`python -m pytest`)
- [ ] Lint clean (`ruff check .`)
- [ ] Format check passes (`ruff format --check .`)
- [ ] Session State updated in AGENTS.md
- [ ] Key decisions documented
- [ ] No secrets or credentials in code
- [ ] Follows ubiquitous language
- [ ] Honest positioning maintained

### Feature Completeness Checklist
- [ ] Feature works as intended
- [ ] Tests cover happy path and edge cases
- [ ] Documentation updated (AGENTS.md, README.md if user-facing)
- [ ] Session State reflects new capability
- [ ] Stakeholder value clear (what does this give them?)

## Collaboration Patterns

### Handoff Protocol
When multiple sessions/agents work on the same project:
1. **Claim**: Update `Current Goal` to show what you're working on
2. **Lock**: If working on a file that others might touch, note it in `Blockers`
3. **Release**: When done, update `Done`, clear `Blockers`, set next `Current Goal`
4. **Verify**: Next session reads Session State and confirms handoff

### Conflict Resolution
If two sessions conflict:
1. Check git history to see what changed
2. Read both sessions' `Key Decisions` to understand rationale
3. Merge changes that align with standards and goals
4. Update Session State to reflect merged state
5. Document the resolution in `Key Decisions`

### Review Protocol
Before accepting significant changes:
1. Does it follow standards? (code, architecture, docs)
2. Does it maintain honest positioning?
3. Does it have tests?
4. Is the stakeholder value clear?
5. Are there any hidden risks or assumptions?

## Implementation Tracking

### Progress Format
Use this format in `## Session State`:

```markdown
### Current Goal
1 line: what we're building right now

### Status
- **Tests**: N passing
- **Lint**: clean/dirty
- **Last session**: 1-line summary

### Done
- [x] What was completed (with date/session if helpful)

### Next (prioritized)
1. [ ] Top priority (dependencies noted)
2. [ ] Second priority
3. [ ] Third priority

### Blockers
- What's blocking progress (or "none")
- Include dependency context if relevant

### Key Decisions This Session
- Important architectural choices made
- Include rationale and alternatives considered
```

### Dependency Tracking
When an item depends on another:
```
2. [ ] Add "review" command (depends on #1: wire --llm flag)
```

### Risk Tracking
When a change has risks:
```
### Blockers
- Risk: SchemaDrivenExtractor may produce malformed prompts for complex graphs
  Mitigation: Add prompt validation before LLM call
  Confidence: Medium
```

## Enforcement Rules

### MUST Do
- Update Session State before every commit
- Run quality gates before every commit
- Document key decisions as they happen
- Follow ubiquitous language
- Maintain honest positioning
- Write tests for new features

### MUST NOT Do
- Commit without tests
- Commit with lint errors
- Use "deterministic" or "compiler" claims
- Generate IaC (CDK/Terraform/CloudFormation)
- Modify extraction/interview/generation core code for new features (use Requirement graph instead)
- Leave Session State stale

### SHOULD Do
- Flag confidence levels on significant changes
- Update README.md for user-facing changes
- Track dependencies in Next list
- Document risks and mitigations
- Follow caveman principles (lean, clear, honest)

### MAY Do
- Add new patterns or catalog entries
- Enhance signal detection
- Improve interview experience
- Add convenience commands

## Trigger Conditions

This skill auto-applies to ALL work. No manual trigger needed.

If you see `## Session State` in AGENTS.md, this skill is active.
If you don't see it, add it before proceeding.
