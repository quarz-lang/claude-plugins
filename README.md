# claude-plugins

Claude Code plugins for working on the [Quarz](https://quarz.dev)
repositories (quarz, pg, rotor, bezel, divider, aws), as a marketplace
named `quarz-lang`.

| Plugin | What it does |
| --- | --- |
| [long-jobs](plugins/long-jobs) | Run or wait for long commands (cargo test, builds, CI) without losing their result; a hook refuses the recurring mistakes |

A repository enables a plugin in its `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "quarz-lang": { "source": { "source": "github", "repo": "quarz-lang/claude-plugins" } }
  },
  "enabledPlugins": { "long-jobs@quarz-lang": true }
}
```
