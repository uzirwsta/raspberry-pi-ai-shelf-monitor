from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHELF_", env_file=".env", extra="ignore")
    mode: str = "demo"
    camera_index: int = 0
    width: int = 1280
    height: int = 720
    fps: int = 8
    confirm_frames: int = 5
    demo_interval: int = 12
    model_path: str = ""
    regions: list[list[float]] = [[.04,.12,.44,.38],[.52,.12,.44,.38],[.04,.53,.44,.38],[.52,.53,.44,.38]]
    products: list[str] = ["Coca-Cola", "Pepsi", "Chips", "Biscuits"]
    database: str = "data/shelf_monitor.db"
    evidence_dir: str = "data/evidence"


settings = Settings()
