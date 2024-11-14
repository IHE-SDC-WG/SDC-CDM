import os


def get_env_var(name: str, default: str = None):
    value = os.environ.get(name, default)
    if value == "":
        print(
            f"Warning: Environment variable {name} is set but has no value,"
            f"defaulting to {default}"
        )
    return value


def get_database_url():
    user = get_env_var("DB_USER", "postgres")
    host = get_env_var("DB_HOST", "localhost")
    port = get_env_var("DB_PORT", "5432")
    name = get_env_var("DB_NAME", "postgres")
    password = os.environ.get("DB_PASSWORD")
    if password is None:
        print("Error: DB_PASSWORD environment variable must be set")
        exit(1)
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
