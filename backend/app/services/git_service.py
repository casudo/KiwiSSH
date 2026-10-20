"""Git operations service using GitPython.

This service handles Git-based configuration storage, including
commits, history retrieval, and diff generation.
"""

import asyncio
import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from git import Repo, Actor, InvalidGitRepositoryError
from git.exc import GitCommandError
from git.remote import PushInfo

from app.core import Settings, get_settings
from app.models.backup import BackupDiff
from app.utils.timezone import get_utc_now


logger = logging.getLogger(__name__)


class GitObjectNotFoundError(ValueError):
    """Raised when a requested commit or config file does not exist in a group's repository."""


class GitService:
    """Service for Git-based configuration storage."""

    ### Backup count and history pages are cached per device: a path-filtered git log has to walk the..
    ## ..group's whole history for rarely changed devices, which gets slow once a group has many commits
    _HISTORY_CACHE_TTL_SECONDS: int = 300
    _HISTORY_PAGE_CACHE_MAX_ENTRIES: int = 512

    def __init__(self) -> None:
        self._repos: dict[str, Any] = {}  # Cache repos by group
        self._repo_locks: dict[str, threading.RLock] = {}
        self._repo_locks_guard = threading.Lock()
        self._history_count_cache: dict[tuple[str, str], tuple[int, float]] = {}
        ### Keyed by (device_name, group, limit, offset), least recently used first
        self._history_page_cache: OrderedDict[tuple[str, str, int, int], tuple[list[dict[str, Any]], float]] = OrderedDict()
        self._history_page_cache_guard = threading.Lock()
        ### Groups with local commits that still need to be pushed (see push_pending)
        self._pending_push_groups: set[str] = set()
        self._pending_push_guard = threading.Lock()
        self._push_locks: dict[str, threading.Lock] = {}

    @property
    def settings(self) -> Settings:
        """Current settings, resolved on every access so a settings reload never leaves a stale copy behind."""
        return get_settings()

    def _get_repo_lock(self, group: str) -> threading.RLock:
        """Get per-group lock guarding GitPython repository access."""
        with self._repo_locks_guard:
            lock = self._repo_locks.get(group)
            if lock is None:
                lock = threading.RLock()
                self._repo_locks[group] = lock
            return lock

    def _get_push_lock(self, group: str) -> threading.Lock:
        """Get per-group lock that keeps two pushes of the same repository from running at once."""
        with self._repo_locks_guard:
            lock = self._push_locks.get(group)
            if lock is None:
                lock = threading.Lock()
                self._push_locks[group] = lock
            return lock

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

    def _read_committed_config(self, repo: Repo, file_name: str) -> str | None:
        """Return a config file's content at HEAD, or None if it has never been committed."""
        if not self._has_commits(repo):
            return None
        try:
            blob = repo.head.commit.tree / file_name
        except KeyError:
            return None

        ### Normalize line endings the same way a text-mode file read does (blobs written on Windows contain CRLF)
        content = blob.data_stream.read().decode("utf-8")
        return content.replace("\r\n", "\n").replace("\r", "\n")

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

    def _save_config_sync(
        self,
        device_name: str,
        config_content: str,
        group: str,
        message: str | None = None,
    ) -> tuple[str, bool, int, int]:
        """
        Save configuration to git repository.

        Args:
            device_name: Name of the device
            config_content: Configuration content to save
            group: Device group (determines which repo)
            message: Commit message (optional, will use template if not provided)

        Returns:
            Tuple of (git commit hash, has_changes, lines_added, lines_removed)
            - has_changes=False means the config is identical to the last backup
        """
        lock = self._get_repo_lock(group)
        with lock:
            repo = self._ensure_repo(group)
            repo_path = self._get_repo_path(group)

            ### Determine file path based on device info
            config_file = repo_path / f"{device_name}.conf"

            ### Compare against the last committed version, not the working tree file
            ## If an earlier commit failed after the file was written, the working tree is already ahead of HEAD..
            ## ..and comparing against it would report "no changes" forever without ever committing that version
            committed_content = self._read_committed_config(repo, config_file.name)
            has_changes = committed_content != config_content

            ### Write config to file if the working tree doesn't already hold it
            working_tree_content = None
            if config_file.exists():
                with open(config_file, "r", encoding="utf-8") as f:
                    working_tree_content = f.read()
            if working_tree_content != config_content:
                with open(config_file, "w", encoding="utf-8") as f:
                    f.write(config_content)

            ### Only commit if there are changes
            if not has_changes:
                ### Working tree had drifted from HEAD (e.g. after a failed commit): re-stage the file so the..
                ## ..stale version can't end up in the next commit of another device in this group
                if working_tree_content != config_content:
                    repo.index.add([config_file.name])
                ### Return a dummy hash and False to indicate no changes
                return ("", False, 0, 0) # TODO: Why do we need the hash here?

            ### Stage the file
            repo.index.add([config_file.name])

            ### Create commit message
            if message is None:
                message = self._render_commit_message(device_name=device_name, group=group)

            ### Commit
            actor = Actor("KiwiSSH Backup System", "backup@kiwissh.local")
            commit = repo.index.commit(message, author=actor, committer=actor)

            ### Evict the device's cached history while still holding the lock, so no request can cache the pre-commit state
            self.invalidate_history_cache(device_name, group)

            ### Don't push here: pushing per commit holds the repo lock during network I/O and..
            ## ..pushes N times for N changed devices. The group is pushed once later instead (see push_pending)
            if self._has_remote_target(group):
                with self._pending_push_guard:
                    self._pending_push_groups.add(group)

            commit_stats = commit.stats.files.get(config_file.name, {})
            lines_added = commit_stats.get("insertions", 0)
            lines_removed = commit_stats.get("deletions", 0)
            return (commit.hexsha, True, lines_added, lines_removed)

    async def save_config(
        self,
        device_name: str,
        config_content: str,
        group: str,
        message: str | None = None,
    ) -> tuple[str, bool, int, int]:
        """Save configuration to git repository without blocking the event loop."""
        return await asyncio.to_thread(
            self._save_config_sync,
            device_name,
            config_content,
            group,
            message,
        )

    def _get_config_history_sync(
        self,
        device_name: str,
        group: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Blocking git history lookup for a device config file.

        Pages are cached for _HISTORY_CACHE_TTL_SECONDS and evicted as soon as a new commit
        is made for the device (see invalidate_history_cache).
        """
        ### Full-history requests (limit=None) aren't cached to keep the cache small
        cache_key = (device_name, group, limit, offset) if limit is not None else None
        if cache_key is not None:
            cached = self._get_cached_history_page(cache_key)
            if cached is not None:
                return cached

        lock = self._get_repo_lock(group)
        with lock:
            ### Check if repo exists and has commits
            repo = self._ensure_repo(group)
            if not self._has_commits(repo):
                return []
            commits: list[dict[str, Any]] = []
            config_file = f"{device_name}.conf"

            commit_kwargs: dict[str, Any] = {"paths": config_file}
            if limit is not None:
                commit_kwargs["max_count"] = limit
            if offset > 0:
                commit_kwargs["skip"] = offset

            try:
                for commit in repo.iter_commits(**commit_kwargs):
                    ### Get file size at this commit
                    file_size_bytes = 0
                    try:
                        file_size_bytes = (commit.tree / config_file).size
                    except KeyError:
                        file_size_bytes = 0

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
            except Exception:
                return []

            ### Reuse the cached count instead of walking the whole history a second time
            total_count = self._get_config_history_count_sync(device_name, group) or len(commits)

            ### Assign version numbers globally - oldest commit = 1, newest = N
            ### Commits are newest first, so reverse the numbering
            for idx, commit in enumerate(commits):
                commit["version_number"] = max(0, total_count - (offset + idx))

            ### Store while holding the repo lock so a concurrent commit can't be overwritten by this older result
            if cache_key is not None:
                self._store_history_page(cache_key, commits)

            return commits

    def _get_cached_history_page(self, cache_key: tuple[str, str, int, int]) -> list[dict[str, Any]] | None:
        """Return a cached history page if it's still within the TTL."""
        with self._history_page_cache_guard:
            cached = self._history_page_cache.get(cache_key)
            if cached is None:
                return None
            if time.monotonic() >= cached[1]:
                del self._history_page_cache[cache_key]
                return None
            self._history_page_cache.move_to_end(cache_key)
            return cached[0]

    def _store_history_page(self, cache_key: tuple[str, str, int, int], commits: list[dict[str, Any]]) -> None:
        """Cache a history page and evict the least recently used pages beyond the size limit."""
        with self._history_page_cache_guard:
            self._history_page_cache[cache_key] = (commits, time.monotonic() + self._HISTORY_CACHE_TTL_SECONDS)
            self._history_page_cache.move_to_end(cache_key)
            while len(self._history_page_cache) > self._HISTORY_PAGE_CACHE_MAX_ENTRIES:
                self._history_page_cache.popitem(last=False)

    async def get_config_history(
        self,
        device_name: str,
        group: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Get configuration history for a device.

        Args:
            device_name: Name of the device
            group: Device group (determines which repo)
            limit: Maximum number of history entries to return. None returns all entries.
            offset: Number of most recent entries to skip (for pagination)

        Returns:
            List of history entries with commit info, file sizes, and version numbers
        """
        return await asyncio.to_thread(self._get_config_history_sync, device_name, group, limit, offset)

    def _get_config_history_count_sync(self, device_name: str, group: str) -> int:
        """Return commit count for a device config file using git rev-list.

        Results are cached for _HISTORY_CACHE_TTL_SECONDS to avoid a git subprocess
        on every request.  The cache entry is evicted immediately when a new commit
        is made for the device (see invalidate_history_cache).
        """
        cache_key = (device_name, group)

        ### Fast path: return cached value if still within TTL (no lock needed for a dict read)
        cached = self._history_count_cache.get(cache_key)
        if cached is not None and time.monotonic() < cached[1]:
            return cached[0]

        lock = self._get_repo_lock(group)
        with lock:
            ### Double-check inside the lock to avoid duplicate git calls from concurrent requests
            cached = self._history_count_cache.get(cache_key)
            if cached is not None and time.monotonic() < cached[1]:
                return cached[0]

            repo = self._ensure_repo(group)
            if not self._has_commits(repo):
                count = 0
            else:
                config_file = f"{device_name}.conf"
                try:
                    count = int(repo.git.rev_list("--count", "HEAD", "--", config_file).strip())
                except (ValueError, GitCommandError):
                    count = 0

            self._history_count_cache[cache_key] = (count, time.monotonic() + self._HISTORY_CACHE_TTL_SECONDS)
            return count

    def invalidate_history_cache(self, device_name: str, group: str) -> None:
        """Evict the cached history count and pages for a device so the next request re-queries git.

        Called right after a new commit is created for the device so the history
        stays accurate without waiting for the TTL to expire.
        """
        self._history_count_cache.pop((device_name, group), None)
        with self._history_page_cache_guard:
            for cache_key in [key for key in self._history_page_cache if key[:2] == (device_name, group)]:
                del self._history_page_cache[cache_key]

    async def get_config_history_count(self, device_name: str, group: str) -> int:
        """Get configuration history count without loading full history."""
        return await asyncio.to_thread(self._get_config_history_count_sync, device_name, group)

    def _get_backup_graph_counts_sync(
        self,
        device_name: str,
        group: str,
        days: int = 365,
        tz_offset_minutes: int = 0,
    ) -> list[dict[str, int | str]]:
        """Return per-day backup counts for the last N days (local dates)."""
        bounded_days = max(1, int(days))
        offset_delta = timedelta(minutes=-int(tz_offset_minutes))

        lock = self._get_repo_lock(group)
        with lock:
            repo = self._ensure_repo(group)
            if not self._has_commits(repo):
                return []
            
            config_file = f"{device_name}.conf"

            ### Calculate cutoff datetime in UTC based on local date boundary
            now_utc = datetime.now(timezone.utc)
            today_local = (now_utc + offset_delta).date()
            start_date = today_local - timedelta(days=bounded_days - 1)
            start_dt_utc = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc) - offset_delta

            ### Try to get commit counts per day via git
            counts: dict[str, int] = {}
            try:
                for commit in repo.iter_commits(paths=config_file, since=start_dt_utc.isoformat()):
                    commit_dt = datetime.fromtimestamp(commit.committed_date, tz=timezone.utc)
                    local_dt = commit_dt + offset_delta
                    if local_dt.date() < start_date:
                        continue

                    ### Count commits when local date is within the last N days
                    date_key = local_dt.date().isoformat()
                    counts[date_key] = counts.get(date_key, 0) + 1
            except Exception:
                return []

            return [
                {"date": date_key, "count": counts[date_key]}
                for date_key in sorted(counts.keys())
            ]

    async def get_backup_graph_counts(
        self,
        device_name: str,
        group: str,
        days: int = 365,
        tz_offset_minutes: int = 0,
    ) -> list[dict[str, int | str]]:
        """Get per-day backup counts for the last N days without full history."""
        return await asyncio.to_thread(
            self._get_backup_graph_counts_sync,
            device_name,
            group,
            days,
            tz_offset_minutes,
        )

    def _get_config_at_commit_sync(self, device_name: str, commit_hash: str, group: str) -> str:
        """Blocking lookup of a config file's content at a specific commit."""
        lock = self._get_repo_lock(group)
        with lock:
            ### Check that repo exists
            repo = self._ensure_repo(group)

            try:
                commit = repo.commit(commit_hash)
            except Exception as e:
                raise GitObjectNotFoundError(f"Commit {commit_hash} not found") from e

            ### Look up the file by path instead of walking the whole tree
            config_file = f"{device_name}.conf"
            try:
                blob = commit.tree / config_file
            except KeyError as e:
                raise GitObjectNotFoundError(f"No config found for {device_name} at commit {commit_hash}") from e
            return blob.data_stream.read().decode("utf-8")

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
            GitObjectNotFoundError: If the commit or the device's config at that commit doesn't exist
        """
        return await asyncio.to_thread(self._get_config_at_commit_sync, device_name, commit_hash, group)

    def _get_commit_info_sync(self, device_name: str, commit_hash: str, group: str) -> dict[str, Any]:
        """Blocking lookup of a single commit's metadata and its version number for a device."""
        lock = self._get_repo_lock(group)
        with lock:
            ### Check that repo exists
            repo = self._ensure_repo(group)

            try:
                commit = repo.commit(commit_hash)
            except Exception as e:
                raise GitObjectNotFoundError(f"Commit {commit_hash} not found") from e

            ### The version number is the count of commits touching the file up to and including this one..
            ## ..which matches the numbering in get_config_history without loading the whole history.
            ## Counting only the newer commits and subtracting them from the cached total keeps recent versions..
            ## ..cheap, instead of walking everything below this commit on every lookup
            config_file = f"{device_name}.conf"
            try:
                newer_count = int(repo.git.rev_list("--count", f"{commit.hexsha}..HEAD", "--", config_file).strip())
                version_number = self._get_config_history_count_sync(device_name, group) - newer_count
            except (ValueError, GitCommandError):
                version_number = None

            committed_at = datetime.fromtimestamp(commit.committed_date, tz=timezone.utc)
            return {
                "hash": commit.hexsha,
                "message": commit.message.strip(),
                "timestamp": committed_at.isoformat(),
                "version_number": version_number,
            }

    async def get_commit_info(self, device_name: str, commit_hash: str, group: str) -> dict[str, Any]:
        """Get metadata (timestamp, message, version number) for a single commit."""
        return await asyncio.to_thread(self._get_commit_info_sync, device_name, commit_hash, group)

    def _get_diff_sync(
        self,
        device_name: str,
        from_commit: str,
        to_commit: str,
        group: str,
    ) -> BackupDiff:
        """Blocking diff between two config versions."""
        lock = self._get_repo_lock(group)
        with lock:
            ### Check if repo exists
            repo = self._ensure_repo(group)

            try:
                from_commit_obj = repo.commit(from_commit)
                to_commit_obj = repo.commit(to_commit)
            except Exception as e:
                raise GitObjectNotFoundError(f"Commits not found: {e}") from e

            ### Generate unified diff scoped to this device file only.
            ### Without path scoping, git includes changes from other devices in the same repo.
            ### The resolved hashes are passed instead of the raw request values so they can never be read as git options
            config_file = f"{device_name}.conf"
            diff_text = repo.git.diff(from_commit_obj.hexsha, to_commit_obj.hexsha, "--", config_file)

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

        Raises:
            GitObjectNotFoundError: If one of the commits doesn't exist
        """
        return await asyncio.to_thread(self._get_diff_sync, device_name, from_commit, to_commit, group)

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

    def _push_group_sync(self, group_name: str) -> bool:
        """
        Push a group's local commits to its remote repository.

        Returns:
            True if push successful (or nothing to push), False otherwise
        """
        with self._get_push_lock(group_name):
            try:
                ### Step 0: Prepare the local repo (remote URL, branch) under the repo lock
                lock = self._get_repo_lock(group_name)
                with lock:
                    repo = self._ensure_repo(group_name)

                    ### Step 0: Check remote target
                    try:
                        remote_url, branch_name = self._resolve_remote_target(group_name)
                    except ValueError as ex:
                        logger.warning("Remote push skipped for group %s: %s", group_name, ex)
                        return True

                    if not self._has_commits(repo):
                        logger.warning(
                            "Remote push skipped for group %s because repository has no commits",
                            group_name,
                        )
                        return True

                    self._ensure_origin_remote(repo, remote_url)

                    try:
                        current_branch = repo.active_branch.name
                    except TypeError:
                        current_branch = None

                    ### Switch to target branch if not already on it
                    if current_branch != branch_name:
                        repo.git.checkout("-B", branch_name)

                ### Step 1: Push outside the repo lock so backups, history and diffs of this group aren't blocked by network I/O
                with Repo(self._get_repo_path(group_name)) as push_repo:
                    push_results = push_repo.remote("origin").push(refspec=f"{branch_name}:{branch_name}")

                if not push_results:
                    logger.error("Remote push returned no result for group %s", group_name)
                    return False

                errors = [
                    result.summary
                    for result in push_results
                    if self._push_result_has_error(result)
                ]

                if errors:
                    logger.error(
                        "Remote push failed for group %s: %s",
                        group_name,
                        "; ".join(errors),
                    )
                    return False

                ### Relief..
                logger.info(
                    "Successfully pushed group %s to remote branch %s",
                    group_name,
                    branch_name,
                )
                return True
            except GitCommandError as ex:
                logger.error(
                    "Remote push failed for group %s: %s",
                    group_name,
                    ex,
                )
                return False
            except Exception as ex:
                logger.error("Remote push failed for group %s: %s", group_name, ex)
                return False

    def has_pending_pushes(self) -> bool:
        """Return True when at least one group has commits that haven't been pushed yet."""
        with self._pending_push_guard:
            return bool(self._pending_push_groups)

    def _push_pending_sync(self) -> None:
        """Push every group that received commits since the last push."""
        with self._pending_push_guard:
            groups = sorted(self._pending_push_groups)
            self._pending_push_groups.clear()

        ### A failed push isn't re-queued here: the group's next commit marks it again
        for group_name in groups:
            self._push_group_sync(group_name)

    async def push_pending(self) -> None:
        """Push all groups with unpushed commits without blocking the event loop."""
        await asyncio.to_thread(self._push_pending_sync)


### Singleton instance
git_service = GitService()
