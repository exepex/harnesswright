---
name: scenario-tester
description: Run the acceptance scenarios of a story against a running build.
allowed-tools: Bash, Read
metadata:
  roles: scenario tester
---

1. Read the story's scenarios.
2. Start the build.
3. Run each scenario and record its result.
4. Use the Task tool to start a subagent that retries each failed scenario once.
5. Report each scenario as passed or failed.
