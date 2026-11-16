# Resolving the profile layers

What we did by hand last week:

1. Read `.harness/profile.yaml` and list its layers in order.
2. Check that each layer's folder exists and holds the version the profile names.
3. Stop and name the layer when one is missing.
4. Merge the layers' rules, later layers first, and write the result to one rules file.
