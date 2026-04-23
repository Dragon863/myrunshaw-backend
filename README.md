# My Runshaw backend

This is the backend for the My Runshaw app. It is a RESTful API built using FastAPI and postgres, documentation is available at [this link](https://runshaw-api.danieldb.uk/docs). All auth is handled by using an Appwrite JWT token. Feel free to use this for your own purposes!

## Testing

The main API container can be tested from `src/api` with Poetry:

- `poetry install --with dev`
- `poetry run pytest`

## Deployment

To run the backend, fill out the required environment variables (examples are provided in the `.env.example` files), then use `docker compose up -d`. You will need to set up a cron job on the host machine to start the sync container every evening, and you may need to adjust the time zone in `docker-compose.yml`. Also ensure you configure an appwrite webhook for both the name cache and user creation/deletion endpoints. It is *strongly* recommended to have each container with external HTTP services behind a reverse proxy; cloudflare tunnels are great for this.

## Development

Use `poetry run fastapi dev -p 5006` in the `src/api` folder to test the main API; you can update `utils/config.dart` in the main flutter project to point to your dev endpoint for testing.

If you want to run the services with local Docker builds instead of the published GHCR images, use the development override:

- `docker compose -f docker-compose.dev.yml up --build`

This keeps the API and name cache on local source mounts, and runs the API with `fastapi dev` for reload-friendly development.

The bus worker and sync engine are opt-in in development because they are background/one-shot jobs:

- `docker compose -f docker-compose.dev.yml --profile workers up --build`

The sync engine can also be run on demand:

- `docker compose -f docker-compose.dev.yml run --rm sync_engine`

Note: the Docker setup still expects the existing `.env` files and any external services they point at (for example Postgres and Redis).