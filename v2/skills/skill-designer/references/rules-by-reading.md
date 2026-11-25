# Writing the rules files by reading

Read this page in step 1.3, when the standards reader's command could not run.

By reading, write only the missing files, and keep a `rules.md` that exists. A new `rules.md` holds the run ID, the
date and the line `not verified: <the reason>`. Write one rules text for each language the profile names, or one named
`core` when there is none, holding the rules you can read from the `rules/core/` and `rules/<language>/` folders of the
release the profile names and the layer folders it lists, and `None.` when there are none (always, when there is no
profile). Start each with the heading `### Changes to rules that reach this run` and one line for each rule a layer
replaces, waives or tightens, as `- <ID> · <title>: replaced by <ID>`, `waived until <date>: <reason>` or
`tightened by <ID>`, or `None.`. End each with the quoted value of `READ_BACK` in `SKILL_DIR/scripts/copyform.py`
(open the file; reading it runs nothing), the line
`Stack: <stack>. Rules in this text: <count>. Last rule: <ID · title, or none>.`, then the quoted value of
`READ_BACK_END`.
