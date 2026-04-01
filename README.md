<div align="center">
  <img alt="Logo" src="readme_images/kiwissh_logo.png"></a>
  <br>
  <h1>KiwiSSH</h1>
  Very cool placeholder text

  ---

  <!-- Placeholder for badges -->
  ![GitHub License](https://img.shields.io/github/license/casudo/KiwiSSH) ![GitHub release (with filter)](https://img.shields.io/github/v/release/casudo/KiwiSSH) ![GitHub action checks](https://img.shields.io/github/check-runs/casudo/KiwiSSH/main) ![GitHub issues](https://img.shields.io/github/issues/casudo/KiwiSSH) ![GitHub last commit](https://img.shields.io/github/last-commit/casudo/KiwiSSH)
</div>

# About KiwiSSH <!-- omit from toc -->

PLACEHOLDER

# Table of Contents <!-- omit from toc -->

- [Features](#features)
- [Supported OS](#supported-os)
- [Screenshots](#screenshots)
- [Installation](#installation)
  - [Bare Metal](#bare-metal)
  - [Docker](#docker)
- [Configuration](#configuration)
  - [Environment Variables](#environment-variables)
  - [Main YAML Config File](#main-yaml-config-file)
    - [Sources](#sources)
      - [File](#file)
      - [PostgreSQL](#postgresql)
    - [Remote Git Locations](#remote-git-locations)
      - [Remote Repository Setup](#remote-repository-setup)
  - [Vendor folder](#vendor-folder)
  - [SSH Profiles YAML file](#ssh-profiles-yaml-file)
- [Future Goals](#future-goals)
- [Technical Documentation](#technical-documentation)
  - [PostgreSQL](#postgresql-1)
- [Development](#development)
- [Legal Disclaimer](#legal-disclaimer)
- [License](#license)
- [Support](#support)

# Features

PLACEHOLDER

# Supported OS

PLACEHOLDER

# Screenshots

PLACEHolder

---

# Installation

## Bare Metal

To run KiwiSSH on your local machine without Docker, follow these steps:

1. Clone the repository
2. Navigate to the backend directory and install the required Python dependencies from `requirements.txt`
3. Set up the `kiwissh.yaml` configuration file in the `config` directory
4. Run the backend using `python entrypoint.py`
5. Navigate to the frontend directory and install the dependencies with `npm install`
6. Start the frontend with `npm run dev`

## Docker

WIP

# Configuration

KiwiSSH can be configured using a combination of environment variables and a [YAML configuration file](config/kiwissh.yaml). The YAML file contains the main configuration settings, while environment variables are used to define global, application-unspecific values for different deployments.

## Environment Variables

See the example [`backend/.env.example`](backend/.env.example) file. Either rename it to `.env` and fill in the values or set the environment variables directly in your deployment environment (e.g. Docker, systemd, etc.). KiwiSSH will automatically load these environment variables on startup.

| Variable Name | Description | Required | Default Value |
| ------------- | ----------- | -------- | ------------- |
| `KIWISSH_LOCAL_TEST_MODE` | If set to true, the application will run in local test mode, which enforces certain config values for easier local testing and development. | **No** | false |
| `TZ` | Timezone for the application. This is used for timestamps in backup job logs and Git commit messages. | **No** | UTC |

## Main YAML Config File

> /config/kiwissh.yaml

The main configuration file [kiwissh.yaml](config/kiwissh.yaml) should explain itself with the comments. For a more detailed understanding of what each segment does, see the headings below.

> [IMPORTANT]
> Changes to the `kiwissh.yaml` file will require a restart of the backend application to take effect.

### Sources

> Where to load the devices to backup from.

Whether you've configured the device source as file or PostgreSQL, the expected format for the device entries should be:

| group  | device_name | ip_address  | enabled |
| ------ | ----------- | ----------- | ------- |
| string | string      | string (IP) | boolean |

#### File

```yaml
sources:
  file: "/config/sources/devices.csv"
```

`sources.file` must be an absolute path.

The devices will be loaded from the specified CSV file. The headers must be seperated by commas like this:

```csv
group,device_name,ip_address,enabled
customer-aaa,router-core-01,10.30.54.1,true
customer-aaa,router-core-02,10.30.54.2,,true
abc-company,switch-dist-01,172.16.28.50,true
abc-company,switch-access-01,172.17.2.34,true
it-department,firewall-01,192.168.1.254,true
```

#### PostgreSQL

```yaml
postgres:
    host: "10.11.12.13"
    port: 5432
    database: "existing_db"
    table: "prod_devices"
    username: "user_readonly"
    password: "supersecret"
```

Make sure that the specified PostgreSQL database and table exist and that the provided user has read access to it.

### Remote Git Locations

> [!NOTE]
> Local git storage is always active to keep track of configuration changes and enable the configuration diff feature.

KiwiSSH creates one git repository per device group in the directory configured via `git.local_path`. To push these commits to a remote repository, you can configure a remote repository via the `git.remote` block. You can also set per-group overrides for the remote repository URL and branch if different groups should push to different repositories or branches.

> [!IMPORTANT]
> > When do I choose the global `git.remote` vs per-group overrides (`groups.<group>.git.remote`)?
>
> **Global:** You should use the global `git.remote` configuration if all your groups should push to the same remote organization/repository structure (for example one repository per group **under the same** organization on GitHub). In this case, you can use the `{group}` placeholder in the global `git.remote.url` to dynamically generate the remote URL for each group based on its name.
> -> Example:`git.remote.url: git@github.com:<YOUR_ORGANIZATION_HERE>/{group}.git` will result in repositories like `<YOUR_ORGANIZATION_HERE>/customer-aaa.git`, `<YOUR_ORGANIZATION_HERE>/abc-company.git`, etc.
>
> **Group overrides:** If your groups belong to different organizations or if you need more granular control over the remote URL each group, setup per-group overrides. In this case, you would leave the global `git.remote` configuration empty (aka remove it) and set the `git.remote.url` and optionally `git.remote.branch` for each group under `groups.<group>.git.remote`.
> -> Example: Group 1 `groups.datacenter-firewalls.git.remote.url: ssh://git@192.168.45.25:222/company-abc/datacenter-firewalls.git`, Group 2 `groups.office-switches.git.remote.url: ssh://git@192.168.45.25:222/company-xyz/office-switches.git`

In the next example, the global `git.remote.url` is configured with a placeholder `{group}` which will be replaced by the actual group name for each group. All groups will use the global template except for `development-firewalls` which has a per-group override for the remote URL, so it will push to the specified SSH URL instead of the global template.

```yaml
git:
  local_path: "/config/backups"
  commit_message_template: "Backup: {group}/{device_name} at {timestamp}"
  remote:
    url: "git@github.com:<YOUR_ORGANIZATION_HERE>/kiwissh-{group}.git"

groups:
  customer-development-firewalls:
    username: "admin"
    password: "password"
    vendor: "forti_os"
    ssh_profile: "modern"
    git:
      remote:
        url: "git@github.com:dev_orga/development-firewalls.git"
        branch: "dev"
```

Available placeholders:

- `commit_message_template`: `{group}`, `{device_name}`, `{timestamp}`
- `git.remote.url`: `{group}`

#### Remote Repository Setup

KiwiSSH uses pushed git commits via SSH to their remote repository. To set up the remote repositories (in general), follow these steps: 

1. Create one remote repository per group.
   - If all groups live under one org, use one global template in `git.remote.url` with `{group}`.
   - If groups are spread across multiple organizations, set per-group overrides under `groups.<group>.git.remote.url`.
2. Ensure the branch from `git.remote.branch` (or per-group branch override) exists or can be created by the push user. Default is `main`.
3. Create an SSH keypair for KiwiSSH if you haven't already and add the public key to your Git provider.
4. Make sure the remote Git user has write access to the repositories
5. Run backup and confirm commits are present locally and remotely.

> [!TIP]
> Since KiwiSSH will use the local OpenSSH client to push commits to the remote repository, the SSH config file (`~/.ssh/config` or `C:\Users\user\.ssh\config`) can be used to manage SSH connection details for the Git provider (e.g. GitHub, GitLab, etc.) and set up things like SSH key usage, custom ports, etc.

## Vendor folder

> /config/vendors

Instructions on how to interact with the vendors CLI are configured inside the `vendors` folder as YAML files. This allows you to easily add support for new vendors by simply adding a new YAML file with the necessary instructions or update the existing ones if the CLI changes without needing to update the backend code.

> [NOTE]
> If you notice changes in the CLI output of your devices after a firmware update, please create an [Issue]() or open a [Pull Request]() with the updated CLI output so we can update the corresponding vendor YAML file and ensure continued compatibility.

WIP explain in more detail what every segment does

> [TIP]
> You can override the vendor of a specific device in the [main YAML config file](#main-yaml-config-file) by adding the device to the `nodes:` segment and adding the `vendor` key.

## SSH Profiles YAML file

> /config/ssh_profiles.yaml

---

# Future Goals

**Short Term:**

- More logging
- Checks for device source: No duplicate hostnames, valid IPs, ... (What if multiple groups hold the same IP address range?)
- SSH Key pair support instead of just passwords
- Override SSH port (Probably better placed in groups/nodes than SSH profiles?)
- Update "Configuration Diff" to not just highlight the affected line (green/red) but also the actual characters which were added/removed (brighter green/red) for better readability

**Mid-term:**

- Make Footer more distinct
- Customizable theme
- Docker Image + GitHub Action to build and push image
- Login Screen, User management and RBAC
- Jumphost support (configurable in YAML config as global, group or node level)
- For real SSH backups: Include time -> We can then display the avg. time as statistic somewhere and seconds needed for backup to the backup list view
- Implement backup job log rotation and retention policies (e.g. delete logs if line >10000 or older than 90 days)
- Add visual popup when opening JobView.vue for the first initial load takes longer than 3 seconds to inform the user that the page is still loading and to prevent them from thinking the UI is frozen
- Move function-level imports to top-level imports to comply with PEP8
- Configuration Diff should show the actual line number of the config file
- Move config validation from `entrypoint.py` to `@field_validator` or `@model_validator` in the Pydantic models in `config.py`. These get directly called when the config is loaded via `get_settings()`. This is the first and fastest way to validate the config. Maybe the entrypoint file is obsolite after that or can be simplified to just validate environment variables. `entrypoint.py` is still useful to check for non-empty fields.
- Pentests
- Rework Pydantic models (required vs optional fields, default values, validators, etc.)

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

---

# Technical Documentation

Placeholder

## PostgreSQL

KiwiSSH will store it's application data in a PostgreSQL database. As of **v0.1.0** this includes backup job logs and favorite devices.

You'll be asked to provide the connection details to your PostgreSQL database in the `kiwissh.yaml` configuration file. KiwiSSH will automatically create the necessary tables on startup.

```yaml
application_database:
  host: "<IP_ADDRESS_OR_HOSTNAME>"
  port: 5432
  database: "your_db_name"
  user: "db_user"
  password: "db_user_password"
```

> [TIP]
> It's recommended to create a separate database user with limited permissions for KiwiSSH to use instead of using a superuser account.

The `backup_jobs` table can grow quite large over time depending on the number of devices and backup frequency. To prevent the database from growing indefinitely, it's recommended to set up a regular maintenance job to clean up old backup job logs that are no longer needed. This can be done using a simple SQL query to delete old records based on a retention policy (e.g., delete logs older than 90 days). **We might implement this as a built-in feature in the future, but for now it's up to the user to set this up.**

> [TIP]
> Consider backing up your PostgreSQL database(s) regularly, independently of KiwiSSH. We recommend [Databasus](https://github.com/databasus/databasus) for that.

# Development

Backend: cd backend, python entrypoint.py
Frontend: cd frontend, npm run dev

> [IMPORTANT]
> If you would like to contribute to the project, please to a look at the [CONTRIBUTING.md](CONTRIBUTING.md) file for guidelines on how to contribute and the code of conduct.

# Legal Disclaimer

Needed?

# License

WIP

# Support

I work on this project in my free time and unpaid. If you find it useful and would like to support its development, consider buying me a coffee:

[![Buy Me a Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/casudo)
