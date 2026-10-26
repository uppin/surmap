---
description: Safely remove local branches that have been pushed to remote
---
# Cleanup Local Branches

This command safely removes local branches that have already been pushed to remote, including backup branches, while preserving the current branch and master.

## Safety Features
- Preserves current branch (whatever you're on)
- Preserves master branch
- Only deletes branches that exist on remote
- Shows preview before deletion
- Includes backup branches in cleanup

## Command

```bash
# Fetch latest from remote
git fetch origin --prune

# Get current branch name
CURRENT_BRANCH=$(git branch --show-current)

# Preview: Show branches that will be deleted
echo "=== Branches to be deleted (exist on remote) ==="
git branch | grep -v "^\*" | grep -v "^  master$" | grep -v "^  $CURRENT_BRANCH$" | while read branch; do
  branch=$(echo "$branch" | xargs)
  if git show-ref --verify --quiet "refs/remotes/origin/$branch"; then
    echo "  - $branch (tracked: origin/$branch)"
  fi
done

# Count branches to delete
BRANCH_COUNT=$(git branch | grep -v "^\*" | grep -v "^  master$" | grep -v "^  $CURRENT_BRANCH$" | while read branch; do
  branch=$(echo "$branch" | xargs)
  if git show-ref --verify --quiet "refs/remotes/origin/$branch"; then
    echo "$branch"
  fi
done | wc -l)

echo ""
echo "Total branches to delete: $BRANCH_COUNT"
echo ""
echo "Current branch: $CURRENT_BRANCH (protected)"
echo "Master branch: master (protected)"
echo ""
read -p "Proceed with deletion? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
  # Delete branches that exist on remote
  git branch | grep -v "^\*" | grep -v "^  master$" | grep -v "^  $CURRENT_BRANCH$" | while read branch; do
    branch=$(echo "$branch" | xargs)
    if git show-ref --verify --quiet "refs/remotes/origin/$branch"; then
      git branch -D "$branch" && echo "Deleted: $branch"
    fi
  done

  echo ""
  echo "✅ Cleanup complete!"
  echo ""
  echo "Remaining branches:"
  git branch
else
  echo "Cleanup cancelled."
fi
```

## Alternative: Delete ALL local branches except current and master

If you want to delete ALL local branches (not just those pushed to remote):

```bash
CURRENT_BRANCH=$(git branch --show-current)

echo "=== All branches except current and master ==="
git branch | grep -v "^\*" | grep -v "^  master$" | grep -v "^  $CURRENT_BRANCH$"

echo ""
read -p "Delete ALL these branches? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
  git branch | grep -v "^\*" | grep -v "^  master$" | grep -v "^  $CURRENT_BRANCH$" | xargs git branch -D
  echo "✅ All branches deleted except $CURRENT_BRANCH and master"
else
  echo "Cleanup cancelled."
fi
```

## Usage

1. Copy the command you want to use
2. Paste into terminal
3. Review the preview list
4. Confirm deletion when prompted
5. Branches are deleted with `-D` flag (force delete)

## Notes

- Uses `-D` flag for force deletion (deletes even if not fully merged)
- Backup branches are included in cleanup
- Safe: always preserves current branch and master
- `git fetch origin --prune` removes stale remote-tracking references first
