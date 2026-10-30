# 09 · Roadmap and open questions

## Phases

Each phase ends with something that works end to end and with evals that prove it. A phase starts only after the
previous one has been reviewed. Everything is built and tested inside harnesswright, on sample projects under
`evals/fixtures/`. Which real repositories adopt the harness, and when, is the owner's decision.

| Phase | Builds | Done when |
|---|---|---|
| **1 · Structure** | These design documents and `AGENTS.md` | The owner approves them |
| **2 · Skill designer** | The skill designer role and skill, adapted from Anthropic's skill-creator; an eval runner that calls host adapters; adapters for Claude Code and OpenAI Codex, and a choice of one open host that can run models from many vendors (see [10 · Skills](10-skills.md)) | The designer produces one small sample skill whose evals pass on two hosts within the portability thresholds |
| **3 · Walking skeleton** | Contract templates; triage, implementer and story judge roles; core standards for `NAME`, `DSGN` and `TEST`; the Java profile; one pipeline (T0 and T1); about ten evals; packaging for each supported host; a small sample Java project under `evals/fixtures/` | A T1 change to the sample Java project runs through the harness on two hosts, and the judge's verdict is checked by a human |
| **4 · Harvest** | A deep read of open-source and vendor skill and agent repositories, each idea scored and recorded with its source and licence | A harvest catalogue the owner has reviewed, mapped onto the rule areas and roles |
| **5 · Standards** | The remaining core areas (`FUNC`, `CONF`, `ERR`, `DOC`, `ITEST`, `PERF`, `SEC`, `OPS`, `PLAN`), written from the harvest in one voice, each with evals | Every core area has rules, checks and evals |
| **6 · Panels** | Reviewer roles, panels, voting, verifier, adjudicator, escalation, metrics; tier T2 | A T2 change to a sample project passes through panels with recorded votes |
| **7 · Planning** | Architect, planner, plan reviewers, story writer, alignment and feature judges, scenario tester, release reviewer; tier T3 | A T3 feature on a sample project goes from request to merge with only the human gates |
| **8 · Second language** | The Python profile, a sample Python project, the onboarding skill, the capability bindings | The Python sample adopts the harness with no change to any core file |
| **9 · Learning** | The curator role and the learning loop; release tooling | A repeated correction becomes an approved rule with an eval |

The skill designer (phase 2) comes first because it makes every later skill. The harvest (phase 4) comes after
the skeleton on purpose: the skeleton fixes the exact shape that harvested ideas must fit. From phase 2 on, the
skill designer also searches for existing skills each time it makes one (see [10 · Skills](10-skills.md)).

## Harvest method (phase 4)

1. **Discover** 100–200 candidate repositories from vendors (Anthropic, OpenAI, Google, Microsoft, GitHub),
   curated lists, plugin marketplaces and searches, by role and by rule area.
2. **Screen** on metadata: a usable licence, real skill or agent files, recent activity, not a bulk catalogue.
3. **Read deeply** the shortlist of 30–40, by cloning each one into a scratch area and reading the actual skill
   files. Nothing from these repositories is installed or run.
4. **Score** each idea against the rule format: is it specific, checkable, reasoned, language-neutral or clearly
   language-specific, and does it cover failure paths?
5. **Label** each kept idea as principle, floor, idiom or choice, with its source, commit and licence.
6. **Synthesise** per area and role: pick the best design, resolve conflicts, list what we must write ourselves.

Candidates already identified, from their published descriptions only (not yet read in depth): anthropics/skills,
obra/superpowers, github/spec-kit, bmad-code-org/BMAD-METHOD, EveryInc/compound-engineering-plugin,
nasimubd/claude-council, deployhq/review-council, wan-huiyan/agent-review-panel, AltimateAI/claude-consensus and
trailofbits/skills.

## Open questions

| # | Question | Default until decided |
|---|---|---|
| 1 | Do run folders stay in the repository after merge, or only in the pull request? | Kept on the branch, removed before merge, summarised in the pull request |
| 2 | Should one panel mix models from different vendors, which sends code to more services? | No: a run uses the models of the host it runs on |
| 3 | Which second language comes first in phase 8? | Python |
| 4 | How is orchestration (sub-agents, parallel work) provided on each host? | Through host adapters, decided in phase 6; steps that need no independence keep a single-agent fallback, and independent steps never run in the implementer's session (`HW-PORT-03`) |
| 5 | Where do organisation and team layers live once they exist: in this repository, or in their own? | In this repository, under `standards/org/` and `standards/team/` |
| 6 | Should a small format check (frontmatter, links, file sizes) run in CI or as a local pre-commit hook? | Neither until the owner asks; checked by agents and review |
| 7 | Which open host runs models from many vendors in phase 2? | Chosen in phase 2, from hosts that read Agent Skills and can run many vendors' models |
