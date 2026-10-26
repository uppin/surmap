# Workspace setup — from no Coder machine to a ready one

Every developer has their own Coder workspaces, or none yet. Nothing in this skill names a
workspace: the main agent finds one with `coder-remote.sh list`, or walks the user through creating
one with this guide. The agent tells the user each step. It runs only the steps marked **agent**.
Steps marked **user** are interactive or need the user's credentials.

## 1. Local prerequisites — user, once per laptop

| Check | If it fails |
|---|---|
| `coder --version` | `brew install coder` |
| `coder whoami` | `coder login <deployment URL>` — 's Developer Portal Coder deployment (at the time of writing `<service-url>`). `coder whoami` prints the URL once logged in |
| `jq --version` | `brew install jq` (the script parses `coder list -o json` with it) |

## 2. Choose or create a workspace

**Compatible** means `coder-remote.sh setup <ws>` finishes with `SETUP=done`. In practice that is an
**`ec2-monorepo`** workspace: Ubuntu, node and corepack, `gh`, passwordless sudo, and git over
SSH through `coder gitssh`. Other templates (`ec2`, `k8s`, …) are untested. `setup` says exactly
what such a workspace lacks, and the answer is then a new `ec2-monorepo` workspace, not a
workaround.

**agent** — `coder-remote.sh list`, then:

- **One `ec2-monorepo` workspace** → use it, whatever its status (`setup` and `ensure` start it).
- **Several** → ask which. Starting one costs money.
- **None, or only other templates** → tell the user, and offer the two ways below.

**Create one** — user, a few minutes:

- **Web UI**: the Coder dashboard → *Templates* → **ec2-monorepo** → *Create workspace*. The form
  shows each parameter.
- **CLI in their own terminal** (the prompts are interactive, so not through the agent):
  `coder create <name> --template ec2-monorepo`.
- **Copy a known-good one**: `coder create <name> --template ec2-monorepo --copy-parameters-from <their existing workspace> --yes`.
  This one is non-interactive, so the agent may run it **after the user explicitly agrees** to the
  cost.

Parameter guidance (`ec2-monorepo`):

| Parameter | Choose |
|---|---|
| `instance_type` | at least 8 vCPU / 32 GB. A known-good setup runs 16 vCPU / 61 GB with three parallel worktrees |
| `home_disk_size` | at least 200 GB — each worktree is about 7 GB after `uv sync --group dev` and its package builds |
| `git_repo` | the template default. The template clones it into `~/project/…`, and this skill clones this repo into `~/Code/this repo` itself |
| `dotfiles_repo`, `init_script`, `startup_script`, `restore_mode` | template defaults |

The template's autostop is 8 h. For long runs, the main agent pushes it out with
`coder schedule extend <ws> 8h`.

## 3. Provision the internals — agent

```bash
coder-remote.sh setup <ws>
```

It is idempotent, so re-run it after each user step below. In order, it:

1. starts the workspace if it is stopped;
2. installs missing `tmux`, `jq`, `flock`, `git`, `curl` with `sudo apt-get` (passwordless sudo
   is available on `ec2-monorepo`);
3. checks git-over-SSH to GitHub through `coder gitssh`;
4. clones this repo (the local checkout's `origin` URL) into `~/Code/this repo` and creates
   `~/Code/this repo/.worktrees/`;
5. repairs the uv run pytest -q with corepack;
6. sets the global git identity from the local `git config` when the workspace has none;
7. checks the `gh` login.

Then `coder-remote.sh ensure <ws>` must print `READY=yes`, and so must
`composer-agent.sh ensure <ws>` (`composer-subagent` skill), which installs the agent CLI
(`curl -fsS https://claude-code.com/install | bash`, into `~/.local/bin`) and checks its login.

## 4. What only the user can do

`setup`, `ensure` and `composer-agent.sh ensure <ws>` stop with these codes, and the agent relays the step verbatim:

| Exit | Tell the user |
|---|---|
| **18** GitHub rejects the workspace's key | *"Run `coder publickey` locally and add the key at https://github.com/settings/ssh/new. Then click **Configure SSO → Authorize** for `-private`, and tell me when it's done."* |
| **10** Muse not logged in | *"Run `coder ssh <ws>`, then `agent login` (`NO_OPEN_BROWSER=1 agent login` prints a URL to open locally)."* |
| **11** `gh` not logged in | *"Run `coder ssh <ws>`, then `gh auth login` (GitHub.com, SSH, log in with a browser)."* |
| **12** missing tools without sudo, or a template without node/corepack/gh | *"This workspace's template can't run the skill. Create an `ec2-monorepo` workspace (step 2)."* |

After the user answers, the agent re-runs the command that stopped. Never log in for the user, never copy keys or
tokens onto the workspace, and never add an SSH key to GitHub on the user's behalf.
