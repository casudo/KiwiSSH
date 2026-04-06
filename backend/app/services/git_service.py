"""Git operations service using GitPython.

This service handles Git-based configuration storage, including
commits, history retrieval, and diff generation.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from git import Repo, Actor, InvalidGitRepositoryError
from git.exc import GitCommandError
from git.remote import PushInfo

from app.core import get_settings
from app.models.backup import BackupDiff
from app.utils.timezone import get_utc_now


logger = logging.getLogger(__name__)


class GitService:
    """Service for Git-based configuration storage."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._repos: dict[str, Any] = {}  # Cache repos by group

    @property
    def backups_base_dir(self) -> Path:
        """Get the base backup directory."""
        return Path(self.settings.git.local_path).resolve()

    def _get_repo_path(self, group: str) -> Path:
        """Get repo path for a specific group."""
        return self.backups_base_dir / group

    def _render_commit_message(self, device_name: str, group: str) -> str:
        """Render commit message from configured template with fallback."""
        timestamp = get_utc_now().isoformat()
        template = self._resolve_commit_message_template(device_name=device_name, group=group)

        try:
            ### Fill in template placeholders
            return template.format(
                device_name=device_name,
                group=group,
                timestamp=timestamp,
            )
        except (KeyError, ValueError) as ex:
            logger.warning(
                "Invalid git.commit_message_template '%s': %s. Falling back to default template.",
                template,
                ex,
            )
            return f"Backup: {device_name} at {timestamp}"

    def _resolve_commit_message_template(self, device_name: str, group: str) -> str:
        """Resolve commit message template with priority: global < group < node."""
        template = self.settings.git.commit_message_template

        ### Check for group overrde
        group_config = self.settings.groups.get(group)
        if group_config is not None and group_config.git is not None:
            group_template = group_config.git.commit_message_template
            if group_template is not None:
                template = group_template

        ### Check for node override
        node_config = self.settings.nodes.get(device_name)
        if node_config is not None and node_config.git is not None:
            node_template = node_config.git.commit_message_template
            if node_template is not None:
                template = node_template

        return template

    def _resolve_remote_target(self, group: str) -> tuple[str, str]:
        """Resolve remote URL and branch with optional per-group overrides."""
        remote_config = self.settings.git.remote
        remote_url = remote_config.url if remote_config is not None else None
        remote_branch = remote_config.branch.strip() if remote_config is not None else "main"

        ### Checks over checks over checks over checks...
        group_config = self.settings.groups.get(group)
        if group_config is not None and group_config.git is not None and group_config.git.remote is not None:
            group_remote = group_config.git.remote
            if group_remote.url is not None:
                remote_url = group_remote.url
            if group_remote.branch is not None:
                remote_branch = group_remote.branch

        if remote_url is None:
            raise ValueError(
                f"No remote URL configured for group '{group}'. "
                "Set git.remote.url or groups.<group>.git.remote.url"
            )

        try:
            ### Fill in {group} placeholder in URL if present, otherwise return as-is
            return (remote_url.format(group=group), remote_branch)
        except KeyError as ex:
            raise ValueError(
                "Invalid placeholder in git.remote.url. Only {group} is supported."
            ) from ex

    def _has_remote_target(self, group: str) -> bool:
        """Return True when a group can resolve to a global or per-group remote URL."""
        global_remote = self.settings.git.remote
        if global_remote is not None and global_remote.url is not None:
            return True

        group_config = self.settings.groups.get(group)
        if group_config is None or group_config.git is None or group_config.git.remote is None:
            return False

        return group_config.git.remote.url is not None

    @staticmethod
    def _push_result_has_error(push_result: PushInfo) -> bool:
        """Return True when a Git push result contains an error flag."""
        error_mask = (
            getattr(PushInfo, "ERROR", 0)
            | getattr(PushInfo, "REJECTED", 0)
            | getattr(PushInfo, "REMOTE_REJECTED", 0)
            | getattr(PushInfo, "REMOTE_FAILURE", 0)
            | getattr(PushInfo, "NO_MATCH", 0)
        )
        return (push_result.flags & error_mask) != 0

    @staticmethod
    def _has_commits(repo: Repo) -> bool:
        """Check whether the repository contains at least one commit."""
        try:
            repo.commit("HEAD")
            return True
        except Exception:
            return False
    def _ensure_origin_remote(self, repo: Repo, remote_url: str):
        """Ensure an origin remote exists and points to configured URL."""
        if any(existing_remote.name == "origin" for existing_remote in repo.remotes):
            remote = repo.remote("origin")
            current_urls = list(remote.urls)
            if not current_urls or current_urls[0] != remote_url:
                remote.set_url(remote_url)
            return remote

        return repo.create_remote("origin", remote_url)

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
                config.set_value("user", "name", "KiwiSSH Backup System")
                config.set_value("user", "email", "backup@kiwissh.local")
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
        repo.index.add([config_file.name])

        ### Create commit message
        if message is None:
            message = self._render_commit_message(device_name=device_name, group=group)

        ### Commit
        actor = Actor("KiwiSSH Backup System", "backup@kiwissh.local")
        commit = repo.index.commit(message, author=actor, committer=actor)

        if self._has_remote_target(group):
            push_ok = await self.push_to_remote(group=group)
            if not push_ok:
                logger.warning(
                    "Local commit created for %s but push to remote failed (group: %s)",
                    device_name,
                    group,
                )

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

    async def push_to_remote(self, group: str | None = None) -> bool:
        """
        Push local commits to remote repository.

        If group is provided, pushes only that group's repository.
        Otherwise pushes all repositories loaded in this process.

        Returns:
            True if push successful, False otherwise
        """
        ### Determine target groups to push
        target_groups: list[str]
        if group is not None:
            target_groups = [group]
        else:
            target_groups = list(self._repos.keys())

        if not target_groups:
            logger.info("Remote push skipped because no repositories are initialized yet")
            return False

        overall_success = True
        attempted_push = False

        ### Iterate over target groups and attempt push if remote is configured
        for group_name in target_groups:
            repo = self._ensure_repo(group_name)

            ### Step 0: Check remote target
            try:
                remote_url, branch_name = self._resolve_remote_target(group_name)
            except ValueError as ex:
                logger.warning("Remote push skipped for group %s: %s", group_name, ex)
                continue

            if not self._has_commits(repo):
                logger.warning(
                    "Remote push skipped for group %s because repository has no commits",
                    group_name,
                )
                continue

            ### Step 1: Push commits to remote and handle errors
            try:
                attempted_push = True
                remote = self._ensure_origin_remote(repo, remote_url)

                try:
                    current_branch = repo.active_branch.name
                except TypeError:
                    current_branch = None

                ### Switch to target branch if not already on it
                if current_branch != branch_name:
                    repo.git.checkout("-B", branch_name)

                push_results = remote.push(refspec=f"{branch_name}:{branch_name}")
                if not push_results:
                    overall_success = False
                    logger.error("Remote push returned no result for group %s", group_name)
                    continue

                errors = [
                    result.summary
                    for result in push_results
                    if self._push_result_has_error(result)
                ]

                if errors:
                    overall_success = False
                    logger.error(
                        "Remote push failed for group %s: %s",
                        group_name,
                        "; ".join(errors),
                    )
                    continue

                ### Relief..
                logger.info(
                    "Successfully pushed group %s to remote branch %s",
                    group_name,
                    branch_name,
                )
            except GitCommandError as ex:
                overall_success = False
                logger.error(
                    "Remote push failed for group %s: %s",
                    group_name,
                    ex,
                )
            except Exception as ex:
                overall_success = False
                logger.error("Remote push failed for group %s: %s", group_name, ex)

        if not attempted_push:
            logger.info("Remote push skipped because no configured remotes had commits to push")
            return False

        return overall_success


### Singleton instance
git_service = GitService()
