<div align="center">
  <img alt="Logo" src="readme_images/kiwissh_logo.png"></a>
  <br>
  <h1>KiwiSSH</h1>
  Backup your network device configurations with ease and keep track of changes.

  ---

  <!-- Placeholder for badges -->
  ![GitHub License](https://img.shields.io/github/license/casudo/KiwiSSH) ![GitHub release (with filter)](https://img.shields.io/github/v/release/casudo/KiwiSSH) ![GitHub action checks](https://img.shields.io/github/check-runs/casudo/KiwiSSH/main) ![GitHub issues](https://img.shields.io/github/issues/casudo/KiwiSSH) ![GitHub last commit](https://img.shields.io/github/last-commit/casudo/KiwiSSH)
</div>

# About KiwiSSH <!-- omit from toc -->

KiwiSSH is a network device configuration backup tool that connects to your devices via SSH, fetches their configurations, and stores them in git repositories for easy version control and change tracking. It also provides a user-friendly web interface to manage your devices, view backup logs, and see configuration changes over time.

It was created as better alternative to RANCID and Oxidized, with a focus on simplicity, ease of use, and modern technologies.

> [!WARNING]
> KiwiSSH is still in early development and may contain bugs and support for only a limited number of vendors. If you want to collaborate, contribute or just have questions, please open an issue or PR.

# Table of Contents <!-- omit from toc -->

- [Features](#features)
- [Supported OS/Device Types](#supported-osdevice-types)
- [Screenshots](#screenshots)
- [Installation](#installation)
  - [Bare Metal](#bare-metal)
  - [Docker](#docker)
- [Configuration](#configuration)
  - [Environment Variables](#environment-variables)
  - [kiwissh.yaml](#kiwisshyaml)
    - [app](#app)
    - [application\_database](#application_database)
    - [sources](#sources)
      - [File](#file)
      - [PostgreSQL](#postgresql)
    - [git](#git)
    - [groups](#groups)
    - [nodes](#nodes)
  - [Vendor folder](#vendor-folder)
    - [Vendor YAML file](#vendor-yaml-file)
      - [vendor](#vendor)
      - [session](#session)
      - [commands](#commands)
      - [processing](#processing)
  - [SSH Profiles YAML file](#ssh-profiles-yaml-file)
- [FAQ](#faq)
  - [How do I setup a remote git location?](#how-do-i-setup-a-remote-git-location)
  - [When do I choose the global `git.remote` vs per-group overrides (`groups.<group>.git.remote`)?](#when-do-i-choose-the-global-gitremote-vs-per-group-overrides-groupsgroupgitremote)
- [Future Goals](#future-goals)
- [Technical Documentation](#technical-documentation)
- [Development](#development)
- [License](#license)
- [Support](#support)

# Features

The frontend offers:

- Dashboard (statistics, favorite devices, overview of KiwiSSH)
- Information-rich device List with filtering, search and favorite option, backup contribution calender, group and vendor belonging , status badge, config diff view and more
- Overview of configured SSH profiles, vendors and groups for easy management and device tracking
- Detailed backup job logs with timestamps, status and error messages for each backup attempt
- Swagger API documentation

The backend provides:

- SSH connectivity to network devices for configuration backup
- Configurable backup schedules with cron expressions on global, group and device level
- Local git repositories for each device group to store configuration history and provide diff view
- Optional remote git repository support to push configuration changes to a central Git server (e.g. GitHub, GitLab, Gitea, etc.)
- Support for loading device lists from CSV files or PostgreSQL databases
- Configurable SSH options and backup commands per vendor, group and device
- Configurable processing rules for captured configurations, including line stripping, cropping and regex-based redaction of sensitive information
- The ability to easily add support for new vendors by creating YAML configuration files that define how to interact with the device CLI and process the output
- RESTful API endpoints for device management, backup job logs and configuration retrieval to enable integration with other tools and automation

# Supported OS/Device Types

For a detailed overview of supported OS/Device types, please refer to the [OS_TYPES.md](OS_TYPES.md) file.

# Screenshots

> [!NOTE]
> Screenshots as of pre-release version v0.1.0

![Dashboard](/readme_images/dashboard.png)

![Device List](/readme_images/devices.png)

![Vendors](/readme_images/vendors.png)

![Groups](/readme_images/groups.png)

![SSH Profiles](/readme_images/ssh_profiles.png)

![Backup Job Logs](/readme_images/backup_jobs.png)

---

# Installation

## Bare Metal

To run KiwiSSH on your local machine without Docker, follow these steps:

1. Clone the repository
2. Navigate to the backend directory and install the required Python dependencies from `requirements.txt`
3. Set up the `kiwissh.yaml` configuration file in the `config/` directory
4. Run the backend using `python entrypoint.py`
5. Navigate to the frontend directory and install the dependencies with `npm install`
6. Start the frontend with `npm run dev`

## Docker

KiwiSSH uses separate Docker images for backend and frontend.

- Backend: FastAPI API service
- Frontend: Nginx serving the built Vue app and proxying `/api/*` to backend

1. Update the [`docker-compose.yaml.example`](docker-compose.yaml.example) with the correct image tags for backend and frontend and set your desired environment variables (optional) and volume mounts. You can find an overview of all available environment variables [here in the README](#environment-variables) or [in the example .env file](backend/.env.example).
2. Run the [`docker-compose.yaml.example`](docker-compose.yaml.example) file
3. Open the UI at `http://<IP>:8123`

> [!IMPORTANT]
> If you're using remote git storages, make sure the SSH keys for the remote git storages are correctly mounted to `/home/kiwissh/.ssh` and the permissions are correct (600 for private key and config file, owned by `kiwissh` running the container) to ensure successful SSH authentication when pushing.

> [!NOTE]
> - API calls are available through the frontend proxy: `http://<IP>:8123/api/v1/...`
> - The mounted `/config` directory must contain `kiwissh.yaml`, `ssh_profiles.yaml`, and `vendors/`

# Configuration

KiwiSSH can be configured using a combination of environment variables and a [YAML configuration file](config/kiwissh.yaml). The YAML file contains the main configuration settings, while environment variables are used to define global, application-unspecific values for different deployments.

## Environment Variables

See the example [`backend/.env.example`](backend/.env.example) file. Either rename it to `.env` and fill in the values or set the environment variables directly in your deployment environment (e.g. Docker, systemd, etc.). KiwiSSH will automatically load these environment variables on startup.

| Variable Name | Description | Required | Default Value |
| ------------- | ----------- | -------- | ------------- |
| `KIWISSH_LOCAL_TEST_MODE` | If set to true, the application will run in local test mode, which enforces certain config values for easier local testing and development. | No | `false` |
| `KIWISSH_CONFIG_DIR` | The directory where the `kiwissh.yaml` configuration file is located. This is used to load the main configuration for the application. | No | `/config` |
| `TZ` | Timezone for the application. This is used for timestamps in backup job logs and Git commit messages. | **No** | `UTC` |

## kiwissh.yaml

> Found at [/config/kiwissh.yaml](config/kiwissh.yaml)

Below you'll find a detailed overview of all available configuration options in the `kiwissh.yaml` file. This file is the main configuration file for KiwiSSH and contains settings for the application, database connection, device sources, git integration, groups and nodes.

> [!IMPORTANT]
> Changes to the `kiwissh.yaml` file will require a restart of the backend application to take effect.

### app

Full available options:

| Key | Description | Required | Default Value |
| --- | ----------- | -------- | ------------- |
| `app.debug` | If set to true, the application will run in debug mode, which enables more verbose logging | No | `false` |
| `app.threads` | The maximum number of concurrent SSH sessions for backups. | No | `20` |
| `app.timeout` | The global SSH timeout in seconds. This can be overridden for specific groups or nodes. | No | `30` |
| `app.retry` | The global SSH retry count, which defines how many additional attempts should be made after the first failed attempt. This can also be overridden for specific groups or nodes. | No | `3` |
| `app.api.host` | The host on which the API server will run. Should be set to 0.0.0.0 when running in Docker. | No | `127.0.0.1` |
| `app.api.port` | The port on which the API server will run. | No | `8000` |
| `app.api.cors_origins` | A list of allowed CORS origins for the API server. | No | `["http://localhost:5173", "http://127.0.0.1:5173"]` |
| `app.schedule.cron` | The cron expression for the global backup schedule. | No | `0 2 * * *` |
| `app.schedule.TZ` | The timezone for the backup schedule. | No | `TZ environment variable or UTC` |

### application_database

The `application_database` segment is used to configure the connection to the PostgreSQL database where KiwiSSH will store its application data (e.g. backup job logs, favorite devices, etc.). This database is required for KiwiSSH to function properly.

> [!IMPORTANT]
> Make sure that the database exists and that the provided user has the necessary permissions to create tables and perform operations on the database. KiwiSSH will automatically create the required tables on startup.

| Key | Description | Required | Default Value |
| --- | ----------- | -------- | ------------- |
| `application_database.host` | The host of the PostgreSQL database. | **Yes** | - |
| `application_database.port` | The port of the PostgreSQL database. | **Yes** | - |
| `application_database.database` | The name of the PostgreSQL database. | **Yes** | - |
| `application_database.username` | The username for the PostgreSQL database. | **Yes** | - |
| `application_database.password` | The password for the PostgreSQL database. | **Yes** | - |

### sources

Configure where KiwiSSH load the devices to backup from. You can choose between loading the devices from a CSV file or from a PostgreSQL database.

> [!IMPORTANT]
> At least one source must be configured. The following columns are required in the device source: `group`, `device_name`, `ip_address`, `enabled`.

#### File

| Key | Description | Required | Default Value |
| --- | ----------- | -------- | ------------- |
| `sources.file` | The absolute path to the CSV file containing the device entries. | **Yes** | - |

The devices will be loaded from the specified CSV file. The headers must be seperated by commas like this:

```csv
group,device_name,ip_address,enabled
prod-firewalls,firewall-prod-01,10.50.240.100,true
prod-firewalls,firewall-prod-02,10.50.240.101,true
test-firewalls,firewall-test-01,10.60.194.10,true
test-firewalls,firewall-test-02,10.60.194.11,true
spine-switches,dc-spine-01,172.16.37.2,true
spine-switches,dc-spine-02,172.16.37.3,true
leaf-switches,dc-leaf-01,172.16.37.4,true
leaf-switches,dc-leaf-02,172.16.37.5,true
leaf-switches,dc-leaf-03,172.16.37.5,true
leaf-switches,dc-leaf-04,172.16.37.6,true
dev-rack,test-c8200-1n-4t,192.168.5.1,true
dev-rack,marketing-catalyst-24p,192.168.5.2,true
dev-rack,sales-catalyst-24p,192.168.5.3,false
```

#### PostgreSQL

> [!IMPORTANT]
> Make sure that the database exists and that the provided user has the necessary permissions to read from the database.

| Key | Description | Required | Default Value |
| --- | ----------- | -------- | ------------- |
| `sources.postgres.host` | The host of the PostgreSQL database containing the device entries. | **Yes** | - |
| `sources.postgres.port` | The port of the PostgreSQL database containing the device entries. | No | `5432` |
| `sources.postgres.database` | The name of the PostgreSQL database containing the device entries. | **Yes** | - |
| `sources.postgres.table` | The name of the PostgreSQL table containing the device entries. | **Yes** | - |
| `sources.postgres.username` | The username for the PostgreSQL database containing the device entries. | **Yes** | - |
| `sources.postgres.password` | The password for the PostgreSQL database containing the device entries. | **Yes** | - |

The `backup_jobs` table can grow quite large over time depending on the number of devices and backup frequency. To prevent the database from growing indefinitely, it's recommended to set up a regular maintenance job to clean up old backup job logs that are no longer needed. This can be done using a simple SQL query to delete old records based on a retention policy (e.g., delete logs older than 90 days). **We might implement this as a built-in feature in the future, but for now it's up to the user to set this up.**

> [!TIP]
> Consider backing up your PostgreSQL database(s) regularly, independently of KiwiSSH. We recommend [Databasus](https://github.com/databasus/databasus) for that.

### git

KiwiSSH will always store the device configurations in local git repositories to provide diff view, history and download options. You can optionally set a remote git location to push the commits (the device config) to.

> [!CAUTION]
> DO NOT delete the "backups" folder ever unless you want to lose all your local git repositories and their history.

| Key | Description | Required | Default Value |
| --- | ----------- | -------- | ------------- |
| `git.local_path` | The local path where the git repositories for the device groups will be stored. | No | `/config/backups` |
| `git.commit_message_template` | The global template for the git commit messages. Available placeholders: `{group}`, `{device_name}`, `{timestamp}`. | No | `"Backup: {group}/{device_name} at {timestamp}"` |
| `git.remote.url` | The global remote git repository URL. Available placeholders: `{group}`. This can be overridden for specific groups. | No | - |
| `git.remote.branch` | The global remote git branch to push to. This can be overridden for specific groups. | No | `main` |

### groups

| Key | Description | Required | Default Value |
| --- | ----------- | -------- | ------------- |
| `groups.<group>.username` | The username for SSH authentication for devices in this group. | **Yes** | - |
| `groups.<group>.password` | The password for SSH authentication for devices in this group. | **Yes** | - |
| `groups.<group>.ssh_profile` | The SSH profile to use for devices in this group. This is used to determine the SSH options to use when connecting to the devices. | **Yes** | - |
| `groups.<group>.vendor` | The vendor of the devices in this group. This is used to determine the CLI commands to run for fetching the configuration. | **Yes** | - |
| `groups.<group>.timeout` | The SSH timeout in seconds for devices in this group. This overrides the global SSH timeout. | No | Global `app.timeout` |
| `groups.<group>.retry` | The SSH retry count for devices in this group. This overrides the global SSH retry count. | No | Global `app.retry` |
| `groups.<group>.schedule.cron` | The cron expression for the backup schedule for devices in this group. This overrides the global backup schedule. | No | Global `app.schedule.cron` |
| `groups.<group>.git.commit_message_template` | The git commit message template for this group. This overrides global `git.commit_message_template`. | No | Global `git.commit_message_template` |
| `groups.<group>.git.remote.url` | The remote git repository URL for this group. This overrides the global `git.remote.url`. | No | Global `git.remote.url` or if set globally |
| `groups.<group>.git.remote.branch` | The remote git branch to push to for this group. This overrides the global `git.remote.branch`. | No | Global `git.remote.branch` if set globally |

### nodes

> [!IMPORTANT]
> Group cannot be overridden on node level.

| Key | Description | Required | Default Value |
| --- | ----------- | -------- | ------------- |
| `nodes.<device_name>.username` | The username for SSH authentication for this device. | No | `groups.<group>.username` |
| `nodes.<device_name>.password` | The password for SSH authentication for this device. | No | `groups.<group>.password` |
| `nodes.<device_name>.ssh_profile` | The SSH profile to use for this device. This is used to determine the SSH options to use when connecting to the device. | No | `groups.<group>.ssh_profile` |
| `nodes.<device_name>.vendor` | The vendor of this device. This is used to determine the CLI commands to run for fetching the configuration. | No | `groups.<group>.vendor` |
| `nodes.<device_name>.timeout` | The SSH timeout in seconds for this device. This overrides the group and global SSH timeout. | No | `groups.<group>.timeout` or Global `app.timeout` |
| `nodes.<device_name>.retry` | The SSH retry count for this device. This overrides the group and global SSH retry count. | No | `groups.<group>.retry` or Global `app.retry` |
| `nodes.<device_name>.schedule.cron` | The cron expression for the backup schedule for this device. This overrides the group and global backup schedule. | No | `groups.<group>.schedule.cron` or Global `app.schedule.cron` |
| `nodes.<device_name>.git.commit_message_template` | The git commit message template for this device. This overrides group and global git commit templates. | No | `groups.<group>.git.commit_message_template` or global `git.commit_message_template` |

## Vendor folder

> Found at `/config/vendors`

Vendor YAML files define how KiwiSSH interacts with each device CLI and how captured output is processed before it is saved.

> [!TIP]
> You can create your own vendor YAML file by copying one of the existing ones and modifying it according to the CLI output of your devices. If you want to contribute your vendor file to the project, please create a Pull Request with the new vendor YAML file in the `config/vendors` folder.

### Vendor YAML file

Each vendor file contains these top-level sections:

- `vendor`: metadata (`id`, `name`, `description`)
- `session`: session-level output settings (currently `comment_prefix`)
- `commands`: command phases (`pre_backup`, `backup`, `post_backup`)
- `processing`: optional output cleanup/redaction rules

Each segment is explained in detail below.

> [TIP]
> You can override the vendor for a specific device in [kiwissh.yaml](#kiwisshyaml) under `nodes.<device_name>.vendor`.

#### vendor

| Key | Description | Required | Default Value |
| --- | ----------- | -------- | ------------- |
| `vendor.id` | A unique identifier for the vendor. | **Yes** | - |
| `vendor.name` | The name of the vendor. | **Yes** | - |
| `vendor.description` | A brief description of the vendor. | No | - |

#### session

| Key | Description | Required | Default Value |
| --- | ----------- | -------- | ------------- |
| `session.comment_prefix` | If set, command outputs will be prefixed with this string and rendered as comments in the saved config file. This is useful for adding metadata like command descriptions or timestamps directly in the config file. | No | `! ` |
| `session.include_metadata_in_config` | Controls whether outputs from `metadata: true` commands are prepended as a block in the saved config. Metadata is always present in the backup job log. | No | `false` |

#### commands

| Key | Description | Required | Default Value |
| --- | ----------- | -------- | ------------- |
| `commands.<phase>` | A list of commands to run in the specified phase. Supported phases are `pre_backup`, `backup`, and `post_backup`. | **Yes** | - |

Steps run in a single interactive shell session in this order: `pre_backup` -> `backup` -> `post_backup`

Each item in the `commands.<phase>` list follows this structure:

```yaml
commands:
  backups:
    - command: "show running-config"
      description: "Get running configuration"
    - command: "another command here"
    - type: "send_input"
      command: "some command that requires input"
      input: "the input to send after the command"
```

You can use the following keys for each command step:

| Key | Description | Required | Default Value |
| --- | ----------- | -------- | ------------- |
| `command` | Directly run the command on the device. | **Either `command` or `type`** | - |
| `type` | Run the command in specified in this item and send the input (`input`) afterwards. If `input` is omitted, the resolved device password will be sent as input. | **Either `command` or `type`** | Must be `send_input` |
| `input` (for `type: "send_input"` only!) | The input to send after the command. This is only used for `send_input` type steps. If omitted, the resolved device password will be sent as input. | No | Resolved device password |
| `description` | A brief description of the command. | No | - |
| `metadata` | If set to true, the output of this command will be saved as comment-prefixed metadata block in the backup job log. This is useful for adding important information to the backup job log. | No | `false` |
| `wait_for_prompt` | If set to false, KiwiSSH will not wait for the command prompt to return after running this command before proceeding to the next step. Use with caution. | No | `true` |
| `show_command_in_config` | If set to true, the command will be included directly in the main config body above its output, prefixed with the comment prefix. This provides better context for the captured output when viewing the saved config file. `show_command_in_config: true` and `metadata: true` cannot be used together and will fail validation. | No | `true` |

#### processing

| Key | Description | Required | Default Value |
| --- | ----------- | -------- | ------------- |
| `processing.strip_patterns` | A list of regex patterns. Lines matching any of these patterns will be removed from the captured config before saving. | No | - |
| `processing.config_start` | A regex pattern that marks the start of the actual configuration in the CLI output. Lines before the matched line will be removed. | No | - |
| `processing.config_end` | A regex pattern that marks the end of the actual configuration in the CLI output. Lines after the matched line will be removed. | No | - |
| `processing.redaction.enabled` | If set to true, the patterns defined in `processing.redaction.patterns` will be applied to the captured config to redact sensitive information. | No | `false` |
| `processing.redaction.patterns` | A list of redaction rules. Each rule should contain a `search` regex pattern, a `replacement` string, and an optional `ignore_case` boolean. | No | - |

> [!IMPORTANT]
> If `ignore_case` is set to true for a redaction rule (default is false), the search pattern will be applied in a case-insensitive manner. Make sure to set this according to the expected CLI output of your devices to ensure effective redaction.

**Processing behavior:**

- `processing` is optional; if no processing options are configured, config output is left unchanged
- `strip_patterns`: remove matching lines
- `config_start` / `config_end`: crop output to boundaries; if one side is missing, file edge is used
- `redaction.enabled` + `redaction.patterns`: apply replacements
- Each redaction rule uses `search`, `replacement`, and optional `ignore_case`

## SSH Profiles YAML file

> Found at `/config/ssh_profiles.yaml`

SSH profiles define reusable options for SSH connections. Assign a profile via `groups.<group>.ssh_profile` and optionally override it per device with `nodes.<device_name>.ssh_profile`.

> [!NOTE]
> **Notes for the usage of** `known_hosts_policy`:
> `strict` validates against `~/.ssh/known_hosts`
> `ignore` skips known-host validation (mapped to `known_hosts: None` in AsyncSSH)
> `auto_add` currently falls back to `ignore` and logs a warning
> Device backup authentication uses username/password from group/node config
> SSH port and timeout are configured in group/node/app settings, not in SSH profiles

You can create your own SSH profile by adding a new entry to the `ssh_profiles.yaml` file. Each profile should have a unique name.

# FAQ

Frequently Asked Questions about the configuration of KiwiSSH.

## How do I setup a remote git location?

KiwiSSH can push local git commits via SSH to their remote repository. To set up the remote repositories (in general), follow these steps:

1. Create one remote repository per group.
   - If all groups live under one org, use one global template in `git.remote.url` with `{group}`.
   - If groups are spread across multiple organizations, set per-group overrides under `groups.<group>.git.remote.url`.
2. Ensure the branch from `git.remote.branch` (or per-group branch override) exists or can be created by the push user. Default is `main`.
3. Create an SSH keypair for KiwiSSH if you haven't already and add the public key to your Git provider.
4. Make sure the remote Git user has write access to the repositories
5. Run backup and confirm commits are present locally and remotely.

> [!TIP]
> Since KiwiSSH will use the local OpenSSH client to push commits to the remote repository, the SSH config file (`~/.ssh/config` or `C:\Users\user\.ssh\config`) can be used to manage SSH connection details for the Git provider (e.g. GitHub, GitLab, etc.) and set up things like SSH key usage, custom ports, etc.
>
> Example: `groups.<group>.git.remote.url: "ssh://git@gitea/customer-aaa/prod-firewalls.git"`
> Config in `~/.ssh/config`:
> ```
> Host gitea
>    HostName 192.168.24.4
>    Port 222
>    User git
>    IdentityFile ~/.ssh/kiwissh-client
> ```

## When do I choose the global `git.remote` vs per-group overrides (`groups.<group>.git.remote`)?

**Global:** You should use the global `git.remote` configuration if all your groups should push to the same remote organization/repository structure (for example one repository per group **under the same** organization on GitHub). In this case, you can use the `{group}` placeholder in the global `git.remote.url` to dynamically generate the remote URL for each group based on its name.
-> Example:`git.remote.url: git@github.com:<YOUR_ORGANIZATION_HERE>/{group}.git` will result in repositories like `<YOUR_ORGANIZATION_HERE>/customer-aaa.git`, `<YOUR_ORGANIZATION_HERE>/abc-company.git`, etc.

**Group overrides:** If your groups belong to different organizations or if you need more granular control over the remote URL each group, setup per-group overrides. In this case, you would leave the global `git.remote` configuration empty (aka remove it) and set the `git.remote.url` and optionally `git.remote.branch` for each group under `groups.<group>.git.remote`.
-> Example: Group 1 `groups.datacenter-firewalls.git.remote.url: ssh://git@192.168.45.25:222/company-abc/datacenter-firewalls.git`, Group 2 `groups.office-switches.git.remote.url: ssh://git@192.168.45.25:222/company-xyz/office-switches.git`

In the next example, the global `git.remote.url` is configured with a placeholder `{group}` which will be replaced by the actual group name for each group. All groups will use the global template except for `development-firewalls` which has a per-group override for the remote URL, so it will push to the specified SSH URL instead of the global template.

```yaml
git:
  local_path: "/config/prod/kiwissh/backups"
  remote:
    url: "ssh://git@github.com:<YOUR_ORGANIZATION_HERE>/kiwissh-{group}.git"

groups:
  development-firewalls:
    username: "admin"
    password: "password"
    vendor: "fortinet_fortigate"
    ssh_profile: "modern"
    git:
      remote:
        url: "ssh://git@github.com:dev_orga/development-firewalls.git"
        branch: "dev"
```

---

# Future Goals

**Short Term:**

- More logging
- Checks for device source: No duplicate hostnames, valid IPs, ... (What if multiple groups hold the same IP address range?)
- SSH Key pair support instead of just passwords
- Override SSH port (Probably better placed in groups/nodes than SSH profiles?)

**Mid-term:**

- Make Footer more distinct
- Customizable theme
- Docker Image + GitHub Action to build and push image
  - Publish Image to Docker hub
- Login Screen, User management and RBAC
- Jumphost support (configurable in YAML config as global, group or node level)
- Implement backup job log rotation and retention policies (e.g. delete logs if line >10000 or older than 90 days)
- Add visual popup when opening JobView.vue if the page load takes longer than 2 seconds to inform the user that the page is still loading and to prevent them from thinking the UI is frozen
- Move function-level imports to top-level imports to comply with PEP8
- Move config validation from `entrypoint.py` to `@field_validator` or `@model_validator` in the Pydantic models in `config.py`. These get directly called when the config is loaded via `get_settings()`. This is the first and fastest way to validate the config. Maybe the entrypoint file is obsolite after that or can be simplified to just validate environment variables. `entrypoint.py` is still useful to check for non-empty fields.
- Pentests
- Rework Pydantic models (required vs optional fields, default values, validators, etc.)
- Rework `tests/`. Include real mock device CLI outputs and uniform sources CSV. Exclude `tests/backups` in .gitignoore. These files can be then freely used by any maintainer to test things out

**Long Term:**

- Switch from package-level imports to absolute imports for better readability and maintainability.
  - **Keep them:** cleaner imports, stable public package API. **Remove them:** more explicit imports, less indirection, but more verbose and tighter coupling to file layout.
- Add CHANGELOG.md to keep track of changes and make it required for external PRs?
- Notification System (Email, Slack, Webhook)
- i18n localization support
- Add yaak API collection
- "Live Log" when pressing "Trigger Backup": Even if not "live live", show the log output as it comes in with nice visual animations and auto-scrolling
- New Update available notification in the UI
- GitHub Wiki for usage?
- Demo version with pre-filled config and mock device sources for users to try out without setting up their own environment (should reset after a certain time or when the user clicks a reset button)
- Migrate /favorites endpoint to /devices?
- For better readibility, add a folder "database" to backend/app/services and place the database related services (backup_job_service, favorite_service) in there (where should source_service.py life?).
- Fix logging strings to use lazy formatting instead of f-strings ([Ruff G004](https://docs.astral.sh/ruff/rules/logging-f-string/)) (Add to ruff.toml)
- Visual diagram of the architecture and how the different components interact with each other (e.g., config loading, backup execution flow, etc.)
- As part of renaming change the theme colors to green-ish
- Swagger API documentation on GitHub Pages
- Allow group passwords to bet set via env vars or other input
- Better device simulation: Add a small script for user to run against actual hardware to create realistic CLI output samples for the vendor YAML file creation. Secrets and sensitive info should be redacted

---

# Technical Documentation

Please visit [TECHNICAL.md](TECHNICAL.md) for detailed technical documentation about the architecture and design decisions of KiwiSSH.

# Development

> [!IMPORTANT]
> If you would like to contribute to the project, please to a look at the [CONTRIBUTING.md](CONTRIBUTING.md) file for guidelines on how to contribute and the code of conduct.

# License

WIP

# Support

I work on KiwiSSH in my free time and unpaid. If you find it useful and would like to support its development, consider supporting me with a coffee:

[![Buy Me a Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/casudo)
