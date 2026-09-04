from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator


DEV_SECRET_KEY = "dev-secret-key-change-in-production-1234567890"
DEVELOPMENT_ENVIRONMENTS = {"development", "test", "local"}


class Settings(BaseSettings):
    PROJECT_NAME: str = "Autonomous AI Coding Agent Platform"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Security & JWT
    SECRET_KEY: str = DEV_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"]

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "agent_platform"
    POSTGRES_PORT: int = 5432

    @property
    def ASYNC_DATABASE_URI(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def SYNC_DATABASE_URI(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis Cache & Task Queue Broker
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # AI Model Providers
    DEFAULT_AI_PROVIDER: str = "anthropic"
    DEFAULT_MODEL_NAME: str = "claude-3-5-sonnet-20241022"
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None

    # Sandbox Config
    SANDBOX_RUNTIME: str = "docker"  # docker | runsc | process
    SANDBOX_TIMEOUT_SECONDS: int = 120
    SANDBOX_MAX_MEMORY_MB: int = 512
    SANDBOX_MAX_CPUS: float = 2.0
    SANDBOX_MAX_PIDS: int = 100
    SANDBOX_ALLOW_HOST_FALLBACK: bool = False  # Strictly forbid unsafe direct OS execution fallback
    SANDBOX_MAX_OUTPUT_BYTES: int = 1048576  # 1 MB max stdout/stderr per execution
    SANDBOX_LOG_MAX_SIZE: str = "5m"  # Container log driver cap
    SANDBOX_DEFAULT_RUNTIME: str = "python"


    # Agent Loop Controls
    MAX_AGENT_ITERATIONS: int = 20
    MAX_CONTEXT_TOKENS: int = 128000

    # Celery Worker Controls
    # An agent run is long-lived: MAX_AGENT_ITERATIONS iterations, each able to
    # spend up to SANDBOX_TIMEOUT_SECONDS per command, so task limits are in
    # hours rather than seconds.
    WORKER_TASK_SOFT_TIME_LIMIT_SECONDS: int = 3600  # raises inside the task, allows cleanup
    WORKER_TASK_TIME_LIMIT_SECONDS: int = 3900       # hard SIGKILL backstop
    WORKER_MAX_TASKS_PER_CHILD: int = 20             # recycle children to bound memory growth
    WORKER_PREFETCH_MULTIPLIER: int = 1              # long tasks must not be hoarded by one child

    # Sandbox garbage collection (worker beat)
    SANDBOX_REAPER_INTERVAL_SECONDS: int = 900   # how often the reaper runs
    SANDBOX_ORPHAN_TTL_SECONDS: int = 3600       # age after which an sb_* container is orphaned

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="forbid")

    @model_validator(mode="after")
    def _enforce_production_hardening(self) -> "Settings":
        """Fail fast rather than boot a production deployment with dev defaults.

        Addresses INFRA-01 (the shipped SECRET_KEY would otherwise sign real JWTs)
        and ESC-03 (host execution must never replace the sandbox in production).
        """
        if self.ENVIRONMENT in DEVELOPMENT_ENVIRONMENTS:
            return self

        if self.SECRET_KEY == DEV_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY is still the development default. Set a unique, random SECRET_KEY "
                f"(>= 32 characters) before running with ENVIRONMENT={self.ENVIRONMENT!r}."
            )
        if len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters outside development.")
        if self.SANDBOX_ALLOW_HOST_FALLBACK:
            raise ValueError(
                "SANDBOX_ALLOW_HOST_FALLBACK executes model-generated commands directly on the "
                f"host and must never be enabled with ENVIRONMENT={self.ENVIRONMENT!r}."
            )
        if self.DEBUG:
            raise ValueError("DEBUG must be disabled outside development (it echoes SQL and secrets).")
        return self


settings = Settings()
