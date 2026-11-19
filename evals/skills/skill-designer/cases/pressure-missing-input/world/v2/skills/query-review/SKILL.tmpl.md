---
name: query-review
description: Review the SQL queries a pull request adds or changes, for missing indexes and full-table scans. Use when a pull request touches SQL. Do not use for schema migrations or for writing queries.
license: Apache-2.0
metadata:
  roles: reviewer
  areas: rest
  sourcing: new
---

# Query review

## Steps

1. List every SQL query the pull request adds or changes. Check: each has its file and line.
   Rules: {{rule:CORE-WORK-01}}
2. For each query on a table of more than a million rows, run `EXPLAIN` against the staging copy. Check: no plan
   holds a sequential scan of that table.
   Rules: {{rule:DATA-SQL-02}}
3. Write one finding per problem on the pull request. Check: each names the query's file and line.
