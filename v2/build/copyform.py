"""The copy form of a rule and of a cited decision point, the copied section of a release skill, and the read-back
block.

Standard library only. The copy form follows reviews/release-design/final-design.md section 2 and the B0.1 plan: a
rule keeps its ID, title, Kind, Rule, Exceptions, Good and Bad, with fixed labels, verbatim and with the rulebook's
line breaks; Bad is labelled "do not do this". A cited decision point keeps its Question, Options and Default, plus a
fixed sentence, so a default is never a plain instruction. Each copied block sits between a begin and an end marker
that carry its ID. A decision point that reaches only by role is not copied here; it reaches through the rules text.
"""

SECTION = "## Rules for this skill"
FLOORS = "### Floors"
OTHERS = "### Other rules"
RULE_PARTS = (("Kind", "Kind"), ("Rule", "Rule"), ("Exceptions", "Exceptions"), ("Good", "Good"),
              ("Bad", "Bad (do not do this)"))
POINT_PARTS = (("Question", "Question"), ("Options", "Options"), ("Default", "Default"))
BINDING = "The binding in your rules text wins; the default applies only when unbound."
READ_BACK = "<!-- read-back -->"
READ_BACK_END = "<!-- end read-back -->"


def begin(rule_id):
    return f"<!-- rule {rule_id} -->"


def end(rule_id):
    return f"<!-- end {rule_id} -->"


def part_lines(rule, name, label):
    """One part as the rulebook writes it, under a fixed label: continuation lines keep their 2-space indent."""
    first, *rest = rule.parts[name]
    return [f"- **{label}:**" + (f" {first}" if first else "")] + [f"  {line}" if line else "" for line in rest]


def block(rule, parts, extra=()):
    lines = [begin(rule.id), f"#### {rule.id} · {rule.title}", ""]
    for name, label in parts:
        if name in rule.parts:
            lines += part_lines(rule, name, label)
    return "\n".join(lines + list(extra) + [end(rule.id)])


def copy_rule(rule):
    """The copy form of a rule that is not a decision point."""
    if rule.is_decision_point:
        raise ValueError(f"{rule.id} is a decision point; use copy_point")
    return block(rule, RULE_PARTS)


def copy_point(rule):
    """The copy form of a decision point a step cites."""
    if not rule.is_decision_point:
        raise ValueError(f"{rule.id} is not a decision point; use copy_rule")
    return block(rule, POINT_PARTS, ["", BINDING])


def rules_section(reached):
    """The one copied section of a release SKILL.md, from a reach.Reach. Rules keep the order they come in."""
    others = [copy_point(r) if r.is_decision_point else copy_rule(r)
              for r in reached.others if not r.is_decision_point or r.id in reached.cited_points]
    floors = [copy_rule(r) for r in reached.floors]
    return "\n\n".join([SECTION, FLOORS] + floors + [OTHERS] + others) + "\n"


def read_back(rules, stack):
    """The block that ends a rules text: its stack, the rule count, and the ID and title of its last rule."""
    last = f"{rules[-1].id} · {rules[-1].title}" if rules else "none"
    return f"{READ_BACK}\nStack: {stack}. Rules in this text: {len(rules)}. Last rule: {last}.\n{READ_BACK_END}\n"
