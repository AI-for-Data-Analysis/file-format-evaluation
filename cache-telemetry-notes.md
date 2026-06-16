# Prompt Cache Telemetry Notes

These notes document an inference from the Codex session telemetry used in this
report. They are meant as analysis notes, not as a polished claim.

## What We Can Compare Cleanly

Total tokens remain comparable across the two worker sessions because they are
the cumulative session accounting reported in the logs:

```text
total_tokens = input_tokens + output_tokens
```

This makes total tokens a useful measure of task footprint: how much model-call
traffic the task accumulated over the session.

## What Is Cache-Confounded

Fresh/non-cached input and API-equivalent cost are less clean because the two
subagent sessions were run sequentially with highly similar prompts.

The first percent-cell worker call appears to have benefited from a prompt cache
that was already warmed by the earlier notebook worker:

| First model call | Input tokens | Cached input | Fresh input |
|---|---:|---:|---:|
| Carson notebook | 43,241 | 4,992 | 38,249 |
| Confucius percent-cell | 43,193 | 41,344 | 1,849 |

The total first-call input sizes were almost identical, but the cached/fresh
split was dramatically different. That difference is unlikely to be caused by
the file format itself. The more plausible explanation is that both prompts
shared a long identical prefix, and the second session was able to reuse cache
state established by the first session.

## Inference About Cache Units

OpenAI's public prompt-caching documentation describes caching as exact prompt
prefix reuse. It does not fully specify every accounting detail exposed in these
Codex logs.

However, the telemetry strongly suggests cached-token accounting is chunked. Many
cached-input values are multiples of 128:

```text
4,992
41,344
42,880
57,728
63,360
67,456
```

Each of those values is divisible by 128. That pattern suggests the cache hit is
not reported at arbitrary single-token precision. It is likely being accounted
for in fixed-size token blocks.

This should be described as an inference from telemetry, not as a documented
OpenAI API guarantee.

## Recommended Report Language

Use total tokens, model calls, tool calls, runtime, and artifact size as primary
evidence.

Use fresh input and API-equivalent cost as secondary, cache-sensitive evidence.

Suggested wording:

> Total-token usage remains comparable because it measures cumulative context
> processed by the session telemetry. Fresh-input and API-cost comparisons are
> less stable because the second worker likely benefited from a prompt cache
> warmed by the first worker's nearly identical prefix.

For future experiments, use repeated AB/BA trials, randomized order, or cache
isolation where possible.
