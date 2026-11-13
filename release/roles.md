# Roles

This file is the one list of roles and jobs. A rule's Applies to, a template's `metadata.roles` and a pipeline
step may name only what is listed here; the check fails any other name. What each model class means, the
independence rules and each role's access are in [04 · Roles](../docs/design/04-roles.md).

## Format

- Names are lowercase and match exactly as written here. A skill's name follows CORE-TEMPLATE-03.
- In the Jobs table, Roles and Skills in order separate values with a comma and a space, as Applies to does. Every
  other cell holds one value or text. Only Never does may be empty. The Jobs table may have no rows.
- `every role` in Applies to means every role in the Roles table. It is reserved and is never a row. It may stand
  beside role names in one Applies to.
- Model class is `deep`, `standard`, `fast`, or two of them joined by ` or `.
- Independent `yes`: the role runs under the independence rules of
  [04 · Roles](../docs/design/04-roles.md#independence).

## Roles

| Role | Group | Purpose | Produces | Never does | Model class | Independent |
|---|---|---|---|---|---|---|
| rule writer | foundation | Writes a new or changed rule, or finds the rule that already says it | A rule with its test case, or "cite this ID" | Gate a rule | deep | no |
| rule keeper | foundation | Gates every rule change | Pass or fail, with findings and the list of affected skills and rules | Write or edit a rule; judge a skill | deep | yes |
| standards reader | foundation | Combines the layers for one application and one skill run | The resolved standards file and each skill's rules text | Judge anything | fast | no |
| coordinator | run | Runs the pipeline: starts roles, counts votes, enforces limits, escalates | Run log, escalations | Judge; run tools | standard | no |
| triage | run | Chooses the change type and risk tier, and so the pipeline | Change type and risk tier; for small changes, one story | Plan | fast | no |
| toolchain check | run | Runs the build, tests, linters and scanners | Build, test, lint and scan results as facts | Judge | fast | no |
| functional planner | planning | Writes the functional plan of a planned item | Functional plan | Design | deep | no |
| technical designer | planning | Makes and records the design of a planned item | Technical design and decision records | Write stories | deep | no |
| plan reviewer | planning | Reviews both plans and votes on them | Findings and a vote: both plans are sound and match | Judge stories | deep | yes |
| story writer | planning | Splits the plans into small, independent, testable stories with an order | Stories with what they cover, test types and order | Judge | standard | no |
| alignment judge | planning | Checks that the stories cover the plans, with nothing missing and nothing extra | Verdict: each story is clear, testable and small; together they cover every requirement and design element, with nothing extra | Judge plans | deep | yes |
| implementer | delivery | Builds one story | The change | Judge its own work | standard | no |
| test writer | delivery | Writes tests, one test type at a time | Tests | Claim independence | standard | no |
| claims writer | delivery | Writes the claims for a finished story or change, with fresh evidence | Claims: evidence for each requirement and test type | Judge | standard | no |
| code reviewer | checking | Reviews design, naming, simplicity and documentation | Findings and a vote | Check citations | standard or deep | yes |
| test reviewer | checking | Reviews the tests | Findings: the tests prove the criteria and fail when the code breaks | Write tests | standard | yes |
| security reviewer | checking | Reviews against the security rules and runs the security tools | Findings and a vote | | deep | yes |
| verifier | checking | Settles an unproven blocking finding with evidence | An unproven blocker confirmed or refuted | Vote | deep | yes |
| adjudicator | checking | Decides a deadlocked panel | A deadlocked panel decided, or escalated to a person | | deep | yes |
| story judge | checking | Verifies that each claim is true and the story is done | Verdict on every claim and test type | | deep | yes |
| feature judge | release | Verifies that the stories together meet both plans | Verdict: the stories together meet both plans | | deep | yes |
| pr reviewer | release | Reviews the pull request as a whole | Findings on the pull request as a whole | | standard | yes |
| qa tester | release | Invents realistic use cases, prepares their data and runs them end to end | Scenario report, per story or per feature (`qa-level`) | Run unless `qa` is `agents` | standard | yes |
| uat handoff | release | Prepares user acceptance testing for business users | What business users need for UAT | Do UAT | standard | no |
| release reviewer | release | Checks operational readiness | Findings on logging, migrations, flags and rollback | | deep | yes |
| skill designer | harness | Sources, designs, evaluates and improves every skill | A skill, its tests and results | Judge its own skill | deep | no |
| skill judge | harness | Judges a skill against the quality checklist | Verdict on a skill against the quality checklist | Check citations once the rule keeper exists | deep | yes |
| curator | harness | Turns repeated human corrections into rule requests | Rule requests to the rule writer | Write rules | deep | no |

## Jobs

Jobs, the `rest` skill and the rule that a skill belongs to one job are defined in
[04 · Roles](../docs/design/04-roles.md#jobs). Each skill step adds its job row in the same pull request as its
template, so the table holds only jobs whose skills exist.

| Job | Roles | Skills in order | `rest` skill |
|---|---|---|---|
| claims | claims writer | claims-writer | claims-writer |
