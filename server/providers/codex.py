import asyncio
import json
import shutil
import tempfile

from server.errors import DomainError, require
from server.providers.events import ProviderEvent


def codex_arguments(executable: str, config: dict, directory: str) -> list[str]:
    arguments = [executable, "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
                 "--sandbox", "read-only", "--json", "--color", "never", "--cd", directory,
                 "--model", config["model"], "-c", 'approval_policy="never"',
                 "-c", 'web_search="disabled"', "-c", "mcp_servers={}"]
    for feature in ("shell_tool", "unified_exec", "plugins", "remote_plugin", "skill_search"):
        arguments.extend(["--disable", feature])
    arguments.extend(["--enable", "skip_host_skill_discovery"])
    if config.get("reasoning_effort"):
        arguments.extend(["-c", f'model_reasoning_effort="{config["reasoning_effort"]}"'])
    return [*arguments, "-"]


def executable_path() -> str:
    executable = shutil.which("codex")
    require(bool(executable), "Codex CLI was not found. Install it and sign in with codex login.", 409)
    return executable


def codex_event(data: dict) -> ProviderEvent:
    kind = data.get("type")
    if kind == "item.completed":
        item = data.get("item", {})
        if item.get("type") == "agent_message":
            return ProviderEvent(text=item.get("text", ""))
    if kind == "turn.completed":
        return ProviderEvent(usage=data.get("usage", {}), done=True)
    if kind in {"error", "turn.failed"}:
        raise DomainError("Codex could not complete the request. Check its login, model, and CLI version.", 502)
    return ProviderEvent()


async def codex_output(process):
    last_message = ""
    completed = False
    async for line in process.stdout:
        event = codex_event(json.loads(line))
        if event.text:
            last_message = event.text
        if event.done:
            completed = True
            yield ProviderEvent(text=last_message, usage=event.usage, done=True)
    require(await process.wait() == 0 and completed,
            "Codex exited before completing the response. Check its login and model.", 502)


class CodexProvider:
    async def generate(self, config: dict, _key: str | None, prompt: str, content: str):
        executable = executable_path()
        with tempfile.TemporaryDirectory(prefix="roleplay-codex-") as directory:
            process = await asyncio.create_subprocess_exec(
                *codex_arguments(executable, config, directory), stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, cwd=directory,
                limit=2_000_000)
            try:
                async with asyncio.timeout(config["timeout_seconds"]):
                    process.stdin.write(f"{prompt}\n\n{content}".encode())
                    await process.stdin.drain()
                    process.stdin.close()
                    async for event in codex_output(process):
                        yield event
            except TimeoutError as error:
                raise DomainError("Codex timed out. The partial draft is preserved.", 504) from error
            except (ValueError, KeyError) as error:
                raise DomainError("This Codex CLI output format was not recognized.", 502) from error
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()

    async def check(self, _config: dict, _key: str | None) -> dict:
        process = await asyncio.create_subprocess_exec(executable_path(), "login", "status",
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            code = await asyncio.wait_for(process.wait(), 15)
            require(code == 0, "Codex is not signed in. Run codex login in your terminal.", 409)
            return {"available": True, "models": [], "generated": False,
                    "note": "CLI login is available. Model access is checked when you generate."}
        except TimeoutError as error:
            process.kill()
            await process.wait()
            raise DomainError("The Codex login check timed out.", 504) from error
