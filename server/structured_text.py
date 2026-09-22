"""Recognize one complete JSON code block without extracting from surrounding prose."""
import re


def json_payload(output: str) -> str:
    match = re.fullmatch(r'\s*```(?:json)?[ \t]*\r?\n(.*?)\r?\n```\s*', output, re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else output
