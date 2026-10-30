# 09 · Roadmap and open questions

## Phases

Each phase ends with something that works end to end and with evals that prove it. A phase starts only after the
previous one has been reviewed.

| Phase | Builds | Done when |
|---|---|---|
| **1 · Structure** | These design documents | The owner approves them |
| **2 · Walking skeleton** | Contract templates; triage, implementer and story judge roles; core standards for `NAME`, `DSGN` and `TEST`; the Java profile; one pipeline (T0 and T1); about ten evals; the Claude Code plugin manifest | A real T1 change in Stratum runs through the harness and the judge's verdict is checked by a human |
| **3 · Harvest** | A deep read of open-source skill and agent repositories, each idea scored and recorded with its source and licence | A harvest catalogue the owner has reviewed, mapped onto the rule areas and roles |
| **4 · Standards** | The remaining core areas (`FUNC`, `CONF`, `ERR`, `DOC`, `ITEST`, `PERF`, `SEC`, `OPS`, `PLAN`), written from the harvest in one voice, each with evals | Every core area has rules, checks and evals |
| **5 · Panels** | Reviewer roles, panels, voting, verifier, adjudicator, escalation, metrics; tiers T2 | A T2 change in Stratum passes through panels with recorded votes |
| **6 · Planning** | Architect, planner, plan reviewers, story writer, alignment and feature judges, scenario tester, release reviewer; tier T3 | A T3 feature goes from request to merge with only the human gates |
| **7 · Second language** | The Python profile, the onboarding skill, the capability bindings | A Python repository adopts the harness with no change to any core file |
| **8 · Learning** | The curator role and the learning loop; release tooling | A repeated correction becomes an approved rule with an eval |

The harvest (phase 3) comes after the skeleton on purpose: the skeleton fixes the exact shape that harvested
ideas must fit.

## Harvest method (phase 3)

1. **Discover** 100–200 candidate repositories from curated lists, plugin marketplaces and searches, by role and
   by rule area.
2. **Screen** on metadata: a usable licence, real skill or agent files, recent activity, not a bulk catalogue.
3. **Read deeply** the shortlist of 30–40, by cloning each one into a scratch area and reading the actual skill
   files. Nothing from these repositories is installed or run.
4. **Score** each idea against the rule format: is it specific, checkable, reasoned, language-neutral or clearly
   language-specific, and does it cover failure paths?
5. **Label** each kept idea as principle, floor, idiom or choice, with its source, commit and licence.
6. **Synthesise** per area and role: pick the best design, resolve conflicts, list what we must write ourselves.

Candidates already identified, from their published descriptions only (not yet read in depth): obra/superpowers,
github/spec-kit, bmad-code-org/BMAD-METHOD, EveryInc/compound-engineering-plugin, nasimubd/claude-council,
deployhq/review-council, wan-huiyan/agent-review-panel, AltimateAI/claude-consensus, trailofbits/skills and
Stratum's own `docs/agents/`.

## Open questions

| # | Question | Default until decided |
|---|---|---|
| 1 | Do run folders stay in the repository after merge, or only in the pull request? | Kept on the branch, removed before merge, summarised in the pull request |
| 2 | Should panels include models from other vendors, which sends code to more services? | Claude models only |
| 3 | Which second language comes first in phase 7? | Python |
| 4 | Does the orchestration use Claude Code's workflow scripts, plain subagents, or both? | Decide in phase 5, after the skeleton shows what is needed |
| 5 | Where do organisation and team layers live once they exist: in this repository, or in their own? | In this repository, under `standards/org/` and `standards/team/` |
| 6 | Should a small format check (frontmatter, links, file sizes) run in CI or as a local pre-commit hook? | Neither until the owner asks; checked by agents and review |
