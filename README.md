<div align="center">
  <img alt="Logo" src="readme_images/multi_device_mockup.png"></a>
  <br>
  <h1>Kiwi SSH</h1>
  Very cool placeholder text

  ---

  <!-- Placeholder for badges -->
  ![GitHub License](https://img.shields.io/github/license/casudo/PLACEHOLDER_URL) ![GitHub release (with filter)](https://img.shields.io/github/v/release/casudo/PLACEHOLDER_URL) ![GitHub action checks](https://img.shields.io/github/check-runs/casudo/PLACEHOLDER_URL/main) ![GitHub issues](https://img.shields.io/github/issues/casudo/PLACEHOLDER_URL) ![GitHub last commit](https://img.shields.io/github/last-commit/casudo/PLACEHOLDER_URL)
</div>

# About Kiwi SSH <!-- omit from toc -->

PLACEHOLDER

# Table of Contents <!-- omit from toc -->

- [Features](#features)
- [Supported OS](#supported-os)
- [Screenshots](#screenshots)
- [Usage](#usage)
  - [Docker](#docker)
- [Future Goals](#future-goals)
- [Technical Documentation](#technical-documentation)
  - [PostgreSQL](#postgresql)
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

# Usage

## Docker

---

# Future Goals

How are Vendors, SSH Profiles filling their data in? Why dont they use /vendors and /ssh_profiles API endpoints?
Add check to entrypoint if SSH profile and vendor is existing and not just set with random str

**Short Term:**

- More logging
- PostgreSQL support for source AND backup job log
- Support for external git storage location (Gitea, GitHub, GitLab, etc.)
- Rename "Project Downtown" to "Kiwi SSH"
- Checks for device source: No duplicate hostnames, valid IPs, ... (What if multiple groups hold the same IP address range?)
- SSH Key pair support instead of just passwords
- Override SSH port (Probably better placed in groups/nodes than SSH profiles?)
- SSH: Timeout/Retry setting
- sources.file.path has no use since its currently hardcoded based on local_test_mode, which shouldnt
- Dark mode needs update: Not everything is using it + make it a little bit lighter
- Backup Job Length Status is capped at 50

**Mid-term:**

- Make Footer more distinct
- Customizable theme
- Docker Image + GitHub Action to build and push image
- Login Screen, User management and RBAC
- Jumphost support
- Threaded/Async backup execution for better performance. Max threads configurable in downtown.yaml
- For real SSH backups: Include time -> We can then display the avg. time as statistic somewhere and seconds needed for backup to the backup list viewW
- Mark favorite decices consistently in database instead of localStorage

**Long Term:**

- Switch from package-level imports to absolute imports for better readability and maintainability.
  - **Keep them:** cleaner imports, stable public package API. **Remove them:** more explicit imports, less indirection, but more verbose and tighter coupling to file layout.
- Add CHANGELOG.md to keep track of changes and make it required for external PRs?
- Notification System (Email, Slack, Webhook)
- i18n localization support
- Dark Mode (global themes files so all colors are in one place?)
- Add yaak API collection
- "Live Log" when pressing "Trigger Backup": Even if not "live live", show the log output as it comes in with nice visual animations and auto-scrolling
- New Update available notification in the UI
- GitHub Wiki for usage?
- Demo version with pre-filled config and mock device sources for users to try out without setting up their own environment (should reset after a certain time or when the user clicks a reset button)
- Remove /redocs from FastAPI and only use OpenAPI 
- /backups/trigger & /backups/trigger/{device} endpoints: They shouldnt wait for response, just return "Backup job triggered for device/group XY". Status and co can be seen in the frontend.

---

# Technical Documentation

Placeholder

## PostgreSQL

placeholder

backup with Databasus

# Development

Backend: cd backend, python entrypoint.py
Frontend: cd frontend, npm run dev

# Legal Disclaimer

Needed?

# License

WIP

# Support

I work on this project in my free time and unpaid. If you find it useful and would like to support its development, consider buying me a coffee:

[![Buy Me a Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/casudo)
