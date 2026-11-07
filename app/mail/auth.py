from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from app.core.config import get_settings
from app.mail.gmail import SCOPES


def authenticate(credentials_path: Path, token_path: Path, scopes: list[str]) -> None:
    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Google credentials file not found at {credentials_path}. "
            "Please follow the instructions in 03_Email_Integration.md to obtain credentials.json."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), scopes=scopes)
    creds = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"Token successfully written to {token_path}")


def main() -> None:
    settings = get_settings()
    authenticate(
        credentials_path=settings.google_credentials_path,
        token_path=settings.google_token_path,
        scopes=SCOPES,
    )


if __name__ == "__main__":
    main()
