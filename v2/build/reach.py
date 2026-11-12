"""Which rules reach one skill run, the jobs that group skills, and the one size count.

Standard library only. This is the one rule of the agreed size design (reviews/release-design/size-final.md,
section 1): a rule reaches a run when, and only when,
  1. it is a floor whose Applies to names one of the run's roles;
  2. its Applies to says "every role";
  3. it is a decision point whose Applies to names one of the run's roles;
  4. it names one of the run's roles and its area is in the skill's areas;
  5. a step of the skill cites it;
  6. it overrides, binds or tightens a rule that reaches the run, applied repeatedly.
Only active rules reach (docs/design/03-standards.md, resolver input 1). Jobs and the `rest` skill follow section 2
of the same design and v2/roles.md. Every failure raises ReachError naming what is wrong.
"""

import re
from dataclasses import dataclass

from rulebook import EVERY_ROLE, NAME, ROLE, RulebookError, split_list

REST = "rest"
AREA = re.compile(NAME)


class ReachError(RulebookError):
    """A skill, job or citation that the one rule cannot place."""


@dataclass(frozen=True)
class Skill:
    name: str
    roles: tuple
    areas: tuple  # area names, or ("rest",)

    @property
    def is_rest(self):
        return self.areas == (REST,)


def size(text):
    """The one count for all three ceilings: Unicode code points."""
    return len(text)


def read_skill(name, frontmatter):
    """A Skill from a template's frontmatter, as rulebook.read_frontmatter returns it."""
    metadata = frontmatter.get("metadata", {})
    roles, areas = split_list(metadata.get("roles", "")), split_list(metadata.get("areas", ""))
    if frontmatter.get("name") != name:
        raise ReachError(f"{name}: frontmatter name is {frontmatter.get('name')!r}, not the folder name")
    if not roles or len(set(roles)) != len(roles) or not all(ROLE.fullmatch(r) and r != EVERY_ROLE for r in roles):
        raise ReachError(f"{name}: metadata.roles must list distinct role names: {metadata.get('roles')!r}")
    rest = areas == [REST]
    if not rest and (not areas or len(set(areas)) != len(areas) or not all(AREA.fullmatch(a) for a in areas)):
        raise ReachError(f"{name}: metadata.areas must be `rest` or distinct area names: {metadata.get('areas')!r}")
    return Skill(name, tuple(roles), tuple(areas))


def check_jobs(jobs, skills):
    """Map each skill name to its job row. jobs is read_roles()["jobs"]; skills maps name -> Skill.

    Fails a job naming an unknown skill, a skill in two jobs or in none, a skill whose roles differ from its job's,
    and a job without exactly one `rest` skill, the one its row names. No jobs and no skills passes.
    """
    owner = {}
    for job_name, row in jobs.items():
        for skill_name in row["Skills in order"]:
            if skill_name not in skills:
                raise ReachError(f"job {job_name} names {skill_name}, which has no template")
            if skill_name in owner:
                raise ReachError(f"{skill_name} is in two jobs: {owner[skill_name]['Job']} and {job_name}")
            if set(skills[skill_name].roles) != set(row["Roles"]):
                raise ReachError(f"{skill_name}: metadata.roles {', '.join(skills[skill_name].roles)} differ from "
                                 f"job {job_name}'s roles {', '.join(row['Roles'])}")
            owner[skill_name] = row
        rest = [s for s in row["Skills in order"] if skills[s].is_rest]
        if rest != [row["`rest` skill"]]:
            raise ReachError(f"job {job_name} needs exactly one `rest` skill, {row['`rest` skill']}; "
                             f"its templates mark {', '.join(rest) or 'none'}")
    for skill_name in skills:
        if skill_name not in owner:
            raise ReachError(f"{skill_name} is in no job")
    return owner


def job(jobs, name):
    """The job row a pipeline step names. Fails an unknown job."""
    if name not in jobs:
        raise ReachError(f"unknown job {name!r}; the roles file lists {', '.join(sorted(jobs)) or 'no jobs'}")
    return jobs[name]


def areas_of(skill, row, skills, rules):
    """The skill's areas. For the `rest` skill: every area of a rule naming one of the job's roles that no other
    skill of the job lists. Decision points have no area here; they reach by item 3."""
    if not skill.is_rest:
        return set(skill.areas)
    listed = {a for s in row["Skills in order"] for a in skills[s].areas}  # `rest` itself is no area
    named = {r.area for r in active(rules) if not r.is_decision_point and set(r.applies_to) & set(row["Roles"])}
    return named - listed


def active(rules):
    return [r for r in rules if r.status == "active"]


@dataclass
class Reach:
    floors: list  # floors, in rulebook order
    others: list  # every other rule that reaches, decision points included, in rulebook order
    cited_points: set  # IDs of decision points a step cites, which get their full copy form

    @property
    def rules(self):
        return self.floors + self.others


def reach(rules, roles, areas, cited):
    """The rules that reach a run of a skill with these roles and areas whose steps cite these IDs.

    rules are in rulebook order, from every layer the caller reads. A cited ID that is not an active rule fails.
    """
    live = active(rules)
    by_id = {r.id: r for r in live}
    for rule_id in cited:
        if rule_id not in by_id:
            known = any(r.id == rule_id for r in rules)
            raise ReachError(f"cited {rule_id} is {'not active' if known else 'not in the rulebook'}")
    roles = set(roles)
    reached = set(cited)
    for rule in live:
        names = set(rule.applies_to)
        if EVERY_ROLE in names or (names & roles and (
                rule.kind in ("floor", "decision point") or rule.area in areas)):
            reached.add(rule.id)
    grew = True
    while grew:
        changers = {r.id for r in live if r.changes in reached and r.id not in reached}
        reached |= changers
        grew = bool(changers)
    kept = [r for r in live if r.id in reached]
    points = {i for i in cited if by_id[i].is_decision_point}
    return Reach([r for r in kept if r.kind == "floor"], [r for r in kept if r.kind != "floor"], points)
