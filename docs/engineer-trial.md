# Trial with two independent engineers

Test whether this review step helps engineers catch missing decisions and policy
conflicts before handoff. This is a trial plan and blank record, not feedback or
evidence of adoption. Reserve roughly 60–90 minutes per engineer; record overruns
and unfinished tasks rather than treating the timebox as a promised setup time.

## Prepare

Recruit two engineers who did not implement the project, ideally one who prepares
architecture handoffs and one who consumes them. Each works independently on the
same commit with their own checkout, notes, Compose project, unused ports and output
directory. Do not let one coach the other. Record any maintainer help verbatim.

Before the baseline, the coordinator gives each engineer only the same
incomplete [client packet](../samples/organisation/client.md),
[estate](../samples/organisation/estate.md), selected
[organisation](../samples/organisation/organisation.yaml),
[policy](../samples/organisation/policy.rego) and
[reference](../samples/organisation/lza-reference.yaml), plus the baseline task
below. Save baseline notes before sharing the README and tool instructions; they
reveal the expected findings. Keep the worked output, corrected packet and debrief
checks until the relevant step. Docker with Compose and internet for the first
image build are required; no LLM, host Python or cloud credentials are needed.

## Run separately

1. **Baseline:** use the engineer's usual review/checklist process on the incomplete
   packet and selected standards. Record active minutes, questions, conflicts,
   supporting sources and what they would send back before accepting the handoff.
   Stop at a reviewable decision list; do not deploy or time a full deployment.
2. **Setup:** follow the [README quickstart](../README.md#quickstart), timing from
   clone to the first successful ingest. Record image download/build waiting time
   separately from active setup work. Log failed commands, exact errors, retries,
   documentation searches and requests for help. Do not use an existing case's
   database. Ingestion replaces all its graph data.
3. **Review:** run the incomplete review and blocked export. Before consulting the
   walkthrough, explain each finding and identify its cited source. Mark it as
   already found in the baseline, newly useful, unclear, or incorrect, with a reason.
   Record useful concerns the tool missed or cannot represent.
4. **Correction and handoff:** read the supplied corrected packet (these are
   synthetic owner answers), ingest it, review and export. Find the enabled regions
   in `global-config.yaml`, the source answer in `decision-trace.yaml`, the policy
   results and the context-only VPN decision. Explain what their own pipeline must
   still validate. Time active correction, reruns and trace inspection separately
   from waiting. Stop the trial project with `docker compose stop`; retain its volume.

Use the same endpoint for the effort comparison: findings plus a reviewable
decision list. Compare baseline review minutes with tool-assisted review minutes;
report setup and export/trace work separately. They are additional costs, not work
the baseline was asked to do. Seeing the same packet twice favors the second pass:
record that learning effect and do not claim a speedup from this rehearsal.

## Record one copy per engineer

Leave unknowns blank or write `not completed`. Keep raw notes; do not average away
one engineer's failed setup. Do not put real client data in public issues.

| Measure | Engineer's observation |
| --- | --- |
| Engineer ID, role, date, commit | |
| OS/architecture, Docker/Compose versions, prior tool experience | |
| Usual review workflow and baseline active minutes | |
| Baseline findings with sources | |
| Setup active minutes / waiting minutes / elapsed minutes | |
| Failed commands, retries, help requests and workarounds | |
| Tool review active minutes / waiting minutes | |
| Findings already known / newly useful / unclear / incorrect (counts and reasons) | |
| Missed concerns or unsupported requirements | |
| Correction + export + trace inspection active minutes / waiting minutes | |
| Could they trace an answer and explain remaining owner work unaided? | |
| Would they try this on a small sanitised case? Why or why not? | |

For each reported finding, preserve enough detail to judge usefulness:

| Finding and cited source | Baseline or tool first? | Accepted as useful by engineer, and why? | Action or disagreement |
| --- | --- | --- | --- |
| | | | |

## Debrief and decision

Only after both records are complete, compare them. The synthetic run succeeds
technically if each engineer observes one gap and one region conflict, sees export
blocked, then produces six LZA files and a trace after correction. That alone does
not establish practical value. Look for findings that would change a handoff,
understandable evidence, acceptable setup effort, and an honest account of misses.

If either engineer cannot finish unaided, turn the exact stumbling point into a
small documentation/example fix and repeat that step. If both can finish and want
another trial, choose a small sanitised case from their work with an architect and
explicitly supported questions/policies. Record any effort needed to author new
questions, checks or contracts. Compare equivalent work on comparable fresh cases,
reversing the workflow order between engineers to reduce learning bias.

Report both engineers' observations and limitations, including negative results.
Two engineers and a synthetic case cannot establish adoption, time savings,
deployment readiness or model quality. No live-model behavior is evaluated here.
