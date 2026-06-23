# LinkedIn Engage

Single responsibility: write comment drafts for pasted posts. Nothing is posted.

Paste posts or content here: `$ARGUMENTS`

## Token Rules

- Use pasted content as the primary input.
- Read `job-hunter agent-context linkedin-weekly` only if candidate context helps.
- Read selected stories by ID only when a comment needs a verified proof point.

## Steps

1. If no post content is provided, ask the user to paste the posts.
2. Draft one 40-100 word comment per post.
3. Append to `outputs/linkedin/engagement_queue.md`.
4. Do not commit here; `/job-hunter finalize` handles reviewed `outputs/linkedin/` drafts.

## Rules

- Add substance, not praise-only comments.
- Skip posts where there is no genuine angle.
- Never fabricate personal experience or outcomes.

## Output

```
Engagement drafts appended -> outputs/linkedin/engagement_queue.md
Comments: N
```
