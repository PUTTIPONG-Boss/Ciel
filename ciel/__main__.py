import uvicorn

from .config import settings


def main() -> None:
    print(f"✦ Ciel is waking up → http://{settings.host}:{settings.port}  (llm={settings.llm}, model={settings.model})")
    uvicorn.run("ciel.main:app", host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
