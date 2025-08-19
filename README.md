# My Runshaw backend

This is the backend for the My Runshaw app. It is a RESTful API built using FastAPI and postgres, documentation is available at [this link](https://runshaw-api.danieldb.uk/docs). All auth is handled by using an Appwrite JWT token. Feel free to use this for your own purposes!

## Testing

The main API container can be tested by installing dependencies from requirements.txt, then running the command `pytest`

## Deployment

To run the backend, fill out the required environment variables (examples are provided in the `.env.example` files), then use `docker compose up -d`. You will need to set up a cron job on the host machine to start the sync container every evening, and you may need to adjust the time zone in `docker-compose.yml`. Also ensure you configure an appwrite webhook for both the name cache and user creation/deletion endpoints. It is *strongly* recommended to have each container with external HTTP services behind a reverse proxy; cloudflare tunnels are great for this.

## Development

Use `fastapi dev -p 5006` in the `src/api` folder to test the main API; you can update `utils/config.dart` in the main flutter project to point to your dev endpoint for testing