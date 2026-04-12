# Contributing to KiwiSSH <!-- omit in toc -->

Thanks for your potential interest in contributing to KiwiSSH! There are several ways you can help improve the project, whether it's through code contributions, documentation, bug reports, or feature requests.

# Table of Contents <!-- omit in toc -->

- [Code of Conduct](#code-of-conduct)
- [Development](#development)
  - [Setup Development Environment](#setup-development-environment)
    - [Local](#local)
    - [Build Docker image yourself](#build-docker-image-yourself)
  - [Swagger API Documentation](#swagger-api-documentation)

---

## Code of Conduct

See the [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) file for our code of conduct, which outlines our expectations for behavior and contributions to the project. Please read and follow the code of conduct to ensure a welcoming and inclusive environment for all contributors.

## Development

> [!IMPORTANT]
> If you are interested in contributing to the development of KiwiSSH, please create an issue and submit a pull request.
> For other inquiries, feel free to contact me -> [casudo](https://github.com/casudo)

Clone/download the repository and follow the [Setup Development Environment](#setup-development-environment) guide.

### Setup Development Environment

To set up a development environment for KiwiSSH, you can either run the backend and frontend locally or build the Docker images yourself. Below are instructions for both approaches.

#### Local

> [!IMPORTANT]
> You will need the following installed on your system:
>
> - Python 3.13+
> - Node.js v24.11+
> - npm 11.6+

To run KiwiSSH on your local machine without Docker, follow these steps:

1. Clone the repository
2. Navigate to the backend directory and install the required Python dependencies from `requirements.txt`
3. Set up the `kiwissh.yaml` configuration file in the `config/` directory
4. Run the backend using `python entrypoint.py`
5. Navigate to the frontend directory and install the dependencies with `npm install`
6. Start the frontend with `npm run dev`

#### Build Docker image yourself

1. Make sure you're in the root of the repository
2. Build the backend image: `docker build -f .\backend\Dockerfile_backend -t casudo/kiwissh-backend:v1.0.1-fix1 .\backend`
3. Build the frontend image: `docker build -f .\frontend\Dockerfile_frontend -t casudo/kiwissh-frontend:v1.0.1-fix1 .\frontend`

> [!TIP]
> The `.dockerignore` file is always resolved from the build context root:
>
> - backend build uses `backend/.dockerignore`
> - frontend build uses `frontend/.dockerignore`

### Swagger API Documentation

The API documentation is available at `http://<IP>:8000/docs` when the backend is running. You can use this interface to explore and test the API endpoints.
