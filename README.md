<div align="center">
  <img alt="Logo" src="readme_images/multi_device_mockup.png"></a>
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
  - [Main YAML config file](#main-yaml-config-file)
    - [Sources](#sources)
      - [File](#file)
      - [PostgreSQL](#postgresql)
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

KiwiSSH will be configured using a combination of environment variables and a YAML configuration file. The YAML file contains the main configuration settings, while environment variables are used to define global, application-unspecific values for different deployments.

## Environment Variables

You will find an overview of the available environment variables in the [`backend/.env.example`](backend/.env.example) file. Either rename it to `.env` and fill in the values or set the environment variables directly in your deployment environment (e.g. Docker, systemd, etc.). KiwiSSH will automatically load these environment variables on startup.

## Main YAML config file

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
- Support for external git storage location (Gitea, GitHub, GitLab, etc.)
- Rename "KiwiSSH" to "Kiwi SSH"
- Checks for device source: No duplicate hostnames, valid IPs, ... (What if multiple groups hold the same IP address range?)
- SSH Key pair support instead of just passwords
- Override SSH port (Probably better placed in groups/nodes than SSH profiles?)
- sources.file.path has no use since its currently hardcoded based on local_test_mode, which shouldnt

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
