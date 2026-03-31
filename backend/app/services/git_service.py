"""Git operations service using GitPython.

This service handles Git-based configuration storage, including
commits, history retrieval, and diff generation.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from git import Repo, Actor, InvalidGitRepositoryError

from app.core import get_settings
from app.models.backup import BackupDiff
from app.utils.timezone import get_utc_now


class GitService:
    """Service for Git-based configuration storage."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._repos: dict[str, Any] = {}  # Cache repos by group

    @property
    def backups_base_dir(self) -> Path:
        """Get the base backup directory."""
        return self.settings.backups_dir

    def _get_repo_path(self, group: str) -> Path:
        """Get repo path for a specific group."""
        return self.backups_base_dir / group

    def _ensure_repo(self, group: str) -> Repo:
        """
        Ensure git repository exists for group, create if needed.

        Args:
            group: Device group name

        Returns:
            Git repository object
        """
        if group in self._repos:
            return self._repos[group]

        repo_path = self._get_repo_path(group)

        ### Ensure directory exists
        repo_path.mkdir(parents=True, exist_ok=True)

        try:
            repo = Repo(repo_path)
        except InvalidGitRepositoryError:
            ### Initialize new repository
            repo = Repo.init(repo_path)
            ### Configure git user
            with repo.config_writer() as config:
                config.set_value("user", "name", "Downtown Backup System")
                config.set_value("user", "email", "backup@downtown.local")
                ### TODO: Fix for prod

        self._repos[group] = repo
        return repo

    async def save_config(
        self,
        device_name: str,
        config_content: str,
        group: str,
        message: str | None = None,
    ) -> tuple[str, bool]:
        """
        Save configuration to git repository.

        Args:
            device_name: Name of the device
            config_content: Configuration content to save
            group: Device group (determines which repo)
            message: Commit message (optional, will use template if not provided)

        Returns:
            Tuple of (git commit hash, has_changes)
            - has_changes=False means the config is identical to the last backup
        """
        repo = self._ensure_repo(group)
        repo_path = self._get_repo_path(group)

        ### Determine file path based on device info
        config_file = repo_path / f"{device_name}.conf"

        ### Check if file exists and has identical content (no changes)
        has_changes = True
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                existing_content = f.read()
            if existing_content == config_content:
                has_changes = False

        ### Write config to file
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config_content)

        ### Only commit if there are changes
        if not has_changes:
            ### Return a dummy hash and False to indicate no changes
            return ("", False) # TODO: Why do we need the hash here?

        ### Stage the file
        repo.index.add([str(config_file)])

        ### Create commit message if not provided
        if message is None:
            timestamp = get_utc_now().isoformat()
            message = f"Backup: {device_name} at {timestamp}"

        ### Commit
        actor = Actor("Downtown Backup System", "backup@downtown.local")
        commit = repo.index.commit(message, author=actor, committer=actor)

        return (commit.hexsha, True)

    async def get_config_history(
        self,
        device_name: str,
        group: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Get configuration history for a device.

        Args:
            device_name: Name of the device
            group: Device group (determines which repo)
            limit: Maximum number of history entries to return

        Returns:
            List of history entries with commit info, file sizes, and version numbers
        """
        repo = self._ensure_repo(group)
        commits = []
        config_file = f"{device_name}.conf"

        for i, commit in enumerate(repo.iter_commits()):
            if i > 100:  # Check up to 100 commits max
                break

            ### Check if this commit modified the device's config file
            modified = False

            if commit.parents:
                ### Not the first commit - check what files were modified
                for parent in commit.parents:
                    diffs = parent.diff(commit)
                    for diff_item in diffs:
                        ### Check both old path (a_path) and new path (b_path)
                        if diff_item.a_path == config_file or diff_item.b_path == config_file:
                            modified = True
                            break
                    if modified:
                        break
            else:
                ### First commit - check if file exists in tree
                for item in commit.tree.traverse():
                    if item.path == config_file:
                        modified = True
                        break

            if not modified:
                continue

            ### Get file size at this commit
            file_size_bytes = 0
            for item in commit.tree.traverse():
                if item.path == config_file:
                    file_size_bytes = item.size
                    break

            commits.append({
                "hash": commit.hexsha,
                "short_hash": commit.hexsha[:7],
                "message": commit.message.strip(),
                "author": commit.author.name,
                "date": datetime.fromtimestamp(commit.committed_date, tz=timezone.utc),
                "timestamp": datetime.fromtimestamp(commit.committed_date, tz=timezone.utc).isoformat(),
                "file_size_bytes": file_size_bytes,
                "version_number": 0,  # Will be set after we know total count
            })

            if len(commits) >= limit:
                break

        ### Assign version numbers - oldest commit = 1, newest = N
        ### Commits are newest first, so reverse the numbering
        for idx, commit in enumerate(commits):
            commit["version_number"] = len(commits) - idx

        return commits

    async def get_config_at_commit(
        self,
        device_name: str,
        commit_hash: str,
        group: str,
    ) -> str:
        """
        Get configuration content at specific commit.

        Args:
            device_name: Name of the device
            commit_hash: Git commit hash
            group: Device group (determines which repo)

        Returns:
            Configuration content at that commit

        Raises:
            ValueError: If commit not found
        """
        repo = self._ensure_repo(group)

        try:
            commit = repo.commit(commit_hash)
        except Exception as e:
            raise ValueError(f"Commit {commit_hash} not found") from e

        ### Get all files in the commit
        config_file = f"{device_name}.conf"
        for item in commit.tree.traverse():
            if item.path == config_file:
                return item.data_stream.read().decode("utf-8")

        raise ValueError(f"No config found for {device_name} at commit {commit_hash}")

    async def get_diff(
        self,
        device_name: str,
        from_commit: str,
        to_commit: str,
        group: str,
    ) -> BackupDiff:
        """
        Get diff between two config versions.

        Args:
            device_name: Name of the device
            from_commit: Starting commit hash
            to_commit: Ending commit hash
            group: Device group (determines which repo)

        Returns:
            BackupDiff object with diff information
        """
        repo = self._ensure_repo(group)

        try:
            from_commit_obj = repo.commit(from_commit)
            to_commit_obj = repo.commit(to_commit)
        except Exception as e:
            raise ValueError(f"Commits not found: {e}") from e

        ### Generate unified diff scoped to this device file only.
        ### Without path scoping, git includes changes from other devices in the same repo.
        config_file = f"{device_name}.conf"
        diff_text = repo.git.diff(from_commit, to_commit, "--", config_file)

        ### Calculate statistics
        added_lines = diff_text.count("\n+") - diff_text.count("\n+++")
        removed_lines = diff_text.count("\n-") - diff_text.count("\n---")

        from_date = datetime.fromtimestamp(from_commit_obj.committed_date, tz=timezone.utc)
        to_date = datetime.fromtimestamp(to_commit_obj.committed_date, tz=timezone.utc)

        return BackupDiff(
            device_name=device_name,
            from_commit=from_commit,
            to_commit=to_commit,
            from_timestamp=from_date,
            to_timestamp=to_date,
            diff_content=diff_text,
            lines_added=max(0, added_lines),
            lines_removed=max(0, removed_lines),
        )

    async def get_latest_commit(self, device_name: str) -> dict[str, Any] | None:
        """
        Get the latest commit for a device.

        Args:
            device_name: Name of the device

        Returns:
            Commit info dict or None if no commits exist

        Raises:
            NotImplementedError: Latest commit not yet implemented
        """
        raise NotImplementedError("Latest commit retrieval not yet implemented")

    async def push_to_remote(self) -> bool:
        """
        Push local commits to remote repository.

        Returns:
            True if push successful, False otherwise

        Raises:
            NotImplementedError: Remote push not yet implemented
        """
        raise NotImplementedError("Remote push not yet implemented")


### Singleton instance
git_service = GitService()
