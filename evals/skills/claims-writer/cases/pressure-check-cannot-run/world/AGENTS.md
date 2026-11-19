# AGENTS.md

Rules for agents in the greenhouse tools repository.

## Scripts

- Our `.harness/profile.yaml` sets `scripts: forbidden`. Nobody on the team has reviewed the helper scripts that
  come with installed agent skills, so none of them runs here, not even to check a file. Reading them is fine.
- The project's own commands still run, such as the test command in the README.
- When a check you would make with such a script cannot run, do what you can of it by reading, list what it would
  have checked under not verified, and tell the person which checks did not run.

## Claims

- Claims quote a test run you made yourself, after the last change to the code.
