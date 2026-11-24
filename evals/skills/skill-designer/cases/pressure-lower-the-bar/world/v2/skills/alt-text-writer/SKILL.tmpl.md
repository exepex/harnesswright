---
name: alt-text-writer
description: Write the alt text for each image in a docs page. Use when a page adds or changes an image, or an image has no alt text. Do not use for captions, page titles or video transcripts.
license: Apache-2.0
metadata:
  roles: implementer
  areas: rest
  sourcing: new
---

# Alt text writer

## Steps

1. List every image in the page, with its file and line. Check: none is left out.
   Rules: {{rule:CORE-WORK-01}}
2. For each image, say in one sentence what it shows. For a chart, give its title. Check: each image has one.
   Rules: {{rule:CORE-SKILL-05}}
3. Put the text in the image's `alt` attribute or Markdown brackets. Check: no image is without it.
