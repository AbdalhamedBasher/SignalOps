"""
Parsing approved runbooks out of Markdown.

Runbooks are written and reviewed by network engineers, not by this codebase,
so the format has to be something they will actually maintain: a title, some
`##` sections, and one `Applies to:` line naming the alarm codes a section
covers. Anything more elaborate would be a format nobody keeps up to date.

Nothing here touches the database. Given text, it returns structure.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

APPLIES_TO_PATTERN = re.compile(r"^applies\s+to\s*:\s*(.+)$", re.IGNORECASE)
SECTION_HEADING = "## "
TITLE_HEADING = "# "


@dataclass
class ParsedSection:
    heading: str
    anchor: str
    body: str
    position: int
    # Alarm codes this section is written for. Empty means it is general
    # guidance rather than advice for a specific fault.
    applies_to: list[str] = field(default_factory=list)


@dataclass
class ParsedRunbook:
    title: str
    sections: list[ParsedSection]


def slugify(heading: str) -> str:
    """`Confirm the transport fault` -> `confirm-the-transport-fault`."""
    lowered = re.sub(r"[^a-z0-9]+", "-", heading.lower())

    return lowered.strip("-")


def parse_runbook(markdown: str, *, fallback_title: str = "Untitled runbook") -> ParsedRunbook:
    title = fallback_title
    sections: list[ParsedSection] = []

    current_heading: str | None = None
    current_codes: list[str] = []
    current_lines: list[str] = []

    def flush() -> None:
        if current_heading is None:
            return

        sections.append(
            ParsedSection(
                heading=current_heading,
                anchor=slugify(current_heading),
                body="\n".join(current_lines).strip(),
                position=len(sections),
                applies_to=list(current_codes),
            )
        )

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()

        if line.startswith(SECTION_HEADING):
            flush()
            current_heading = line[len(SECTION_HEADING) :].strip()
            current_codes = []
            current_lines = []
            continue

        if line.startswith(TITLE_HEADING):
            title = line[len(TITLE_HEADING) :].strip()
            continue

        if current_heading is None:
            continue

        applies_to = APPLIES_TO_PATTERN.match(line.strip())

        if applies_to is not None and not current_codes:
            current_codes = [
                code.strip().upper()
                for code in applies_to.group(1).split(",")
                if code.strip()
            ]
            continue

        current_lines.append(line)

    flush()

    return ParsedRunbook(title=title, sections=sections)


def load_runbook_directory(directory: Path) -> list[tuple[str, ParsedRunbook]]:
    """
    Read every Markdown runbook in a directory, sorted for a stable order.

    Returns pairs of (source file name, parsed runbook) so the origin of every
    section can be recorded — a citation nobody can trace back to a file is not
    much of a citation.
    """
    parsed: list[tuple[str, ParsedRunbook]] = []

    for path in sorted(directory.glob("*.md")):
        parsed.append(
            (
                path.name,
                parse_runbook(
                    path.read_text(encoding="utf-8"), fallback_title=path.stem
                ),
            )
        )

    return parsed
