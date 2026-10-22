if (!(Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv package manager..."
    irm https://astral.sh/uv/install.ps1 | iex
}
Write-Host "Starting Computer Use SubQ Voice Agent..."
uv run python run_agent.py
