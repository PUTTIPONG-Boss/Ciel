import uvicorn

from .config import settings
from .version import info


def main() -> None:
    v = info()
    print(f"✦ Ciel v{v['version']} ({v['commit'] or 'no git'}) → http://{settings.host}:{settings.port}  (llm={settings.llm}, model={settings.model})")
    uvicorn.run(
        "ciel.main:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
        timeout_graceful_shutdown=5,  # don't let open chats block an auto-update restart
    )


if __name__ == "__main__":
    main()
