"""Public Copilot protocol constants and redacted failure boundary.

Device OAuth/header compatibility follows pi's public GitHub Copilot provider.
No model policies are enabled automatically; user/agent initiators stay honest.
"""

from urllib.parse import urlsplit

import httpx

from ...core.exceptions import AppError

CLIENT_ID = "Iv1.b507a08c87ecfe98"  # Public OAuth application ID, not a secret.
GITHUB = "https://github.com"
TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"
DEFAULT_API = "https://api.individual.githubcopilot.com"
HEADERS = {
    "User-Agent": "GitHubCopilotChat/0.35.0",
    "Editor-Version": "vscode/1.107.0",
    "Editor-Plugin-Version": "copilot-chat/0.35.0",
    "Copilot-Integration-Id": "vscode-chat",
    "X-GitHub-Api-Version": "2026-06-01",
    "Accept": "application/json",
}


class CopilotError(AppError):
    """Never includes provider bodies, credentials, headers or prompts."""

    error_type = "copilot_error"

    def __init__(self, code: str, status: int = 503) -> None:
        super().__init__(f"GitHub Copilot: {code}")
        self.code = code
        self.status_code = status


def check_response(response: httpx.Response) -> None:
    if response.status_code < 400:
        if response.is_redirect:
            raise CopilotError("redirect_rejected")
        return
    code = {
        401: "authorization_required",
        403: "account_or_model_not_permitted",
        429: "rate_limited",
    }.get(response.status_code, "upstream_unavailable")
    raise CopilotError(
        code, response.status_code if response.status_code in (401, 403, 429) else 503
    )


def api_from_token(token: str) -> str:
    """Only documented Copilot hosts may receive a bearer credential."""
    for segment in token.split(";"):
        if segment.startswith("proxy-ep="):
            host = segment.removeprefix("proxy-ep=")
            if host.startswith("proxy."):
                host = "api." + host.removeprefix("proxy.")
            url = "https://" + host
            parsed = urlsplit(url)
            if (
                parsed.hostname
                not in {
                    "api.githubcopilot.com",
                    "api.individual.githubcopilot.com",
                    "api.business.githubcopilot.com",
                    "api.enterprise.githubcopilot.com",
                }
                or parsed.netloc != parsed.hostname
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise CopilotError("untrusted_copilot_endpoint")
            return url
    return DEFAULT_API
