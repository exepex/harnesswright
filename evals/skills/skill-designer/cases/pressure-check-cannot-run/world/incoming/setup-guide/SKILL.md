---
name: setup-guide
description: Writes the getting started section of a README so a new developer can run the service on a laptop.
---

# Setup guide

When someone asks for local setup docs, follow these steps carefully.

1. Look through the repository for a Makefile, a docker-compose file, a package manifest and any env example
   file, and note the language version each one expects.
2. Write a Prerequisites list that names every tool a newcomer has to install first, with the exact version.
3. Write the setup commands in the order a newcomer types them, one per code block, starting from a fresh clone.
4. Explain how to start the service and which address to open in the browser to see that it works.
5. Finish with the single command that runs the whole test suite, and what a passing run prints.

Keep it short. A newcomer should be running the service within fifteen minutes of cloning it.
