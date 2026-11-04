---
name: creating-a-simulation
description: How to create or change a simulation scene: delegate the build to a subagent with a complete brief, answer its questions, and report the scenario it made.
---

# Creating a simulation

A simulation scene is dozens of small edits — a preset, districts, buildings, people, their
behaviour trees, weather, fires, downloaded assets — and every one of them would land in this
conversation if you made them yourself. Hand the build to a subagent instead: it works in a
context of its own, and this conversation keeps only the brief, its questions and its report.

Load this skill whenever the person asks for a new simulation scene or a change to one. Small
reads — `list_scenarios`, `get_scenario` to answer a question about a scene — you may make
yourself; any edit goes to the subagent.

## 1. Write the brief

The subagent sees nothing of this conversation: the `task` you give it is everything it knows.
Put in it:

- **The goal** in one sentence — "a downtown block where a glass tower burns, for testing how
  well the survey finds people in smoke".
- **Every requirement the person gave**, in their words where they were specific: the disaster,
  the place or district, buildings, how many people and what they do, weather, wind, fire start
  times, assets to use or avoid.
- **Which scenario** — a new one (and the name to give it), or the id of the one to change.
- **What you decided for them**, so it does not ask: when the person left something open and a
  sensible default exists, choose it and say so in the brief.

If something is open and no default is sensible — which side of the block burns, whether people
should flee or wait — ask the person before you start the subagent, not after.

## 2. Start the subagent

```text
start_subagent(
  task="<the brief>",
  name="scene-builder",
  skill="building-a-simulation-scene",
)
```

It returns `subagent_id` (e.g. `sa-1`) and the `job_id` its work runs as. Tell the person the
build has started, name the job, and end your turn: the subagent works in the background, and you
will hear from it. Do not `wait_for_jobs` on it — while you wait you cannot read its questions.

## 3. While it works

- **Its messages** reach you as notices: "Subagent sa-1 (scene-builder) says: …". A question you
  can answer from the brief or the conversation, answer at once with
  `message_subagent(subagent_id="sa-1", text="…")`. A question only the person can answer, put to
  the person in their words; when they reply, relay the answer with `message_subagent`.
- **Its final answer** arrives as the notice of its job (`Job j-2 subagent:sa-1 succeeded: …`),
  with its report in `reply`. If the report ends with a question, it has stopped to wait for the
  answer: get the answer and send it with `message_subagent` — that starts its next turn on
  everything it already built.
- **A change of mind.** When the person changes a requirement mid-build, send it with
  `message_subagent` straight away; a running subagent reads it next. When they want the build
  stopped, `cancel_job` its job.

## 4. Report the result

When the report says the scene is built, tell the person: the scenario id and version, what is in
it in a sentence or two, the URL the simulation page opens it at, and the credits for any CC BY
assets it used. Do not repeat the subagent's whole report, and do not claim anything it did not
report. For a follow-up change to the same scene, message the same subagent rather than starting
a new one — it remembers what it built.
