"""Group a unified diff of the config by TOML section."""

import re

import tomlkit

from .layout import header_path


def group_diff_by_section(diff, new_text):
    """Split unified-diff hunks by the TOML section containing their new lines."""
    section_by_line = {}
    section = "Top-level settings"
    for line_number, line in enumerate(new_text.splitlines(), start=1):
        if line.lstrip().startswith("["):
            try:
                path, is_array = header_path(line)
            except (tomlkit.exceptions.TOMLKitError, ValueError):
                path, is_array = (), False
            if path:
                section = ("[[" if is_array else "[") + ".".join(map(str, path)) + ("]]" if is_array else "]")
        section_by_line[line_number] = section

    groups = {}
    lines = diff.splitlines(keepends=True)
    index = 0
    while index < len(lines):
        if not lines[index].startswith("@@ "):
            index += 1
            continue
        hunk = [lines[index]]
        match = re.search(r"\+(\d+)(?:,\d+)?", lines[index])
        new_start = int(match.group(1)) if match else 1
        index += 1
        while index < len(lines) and not lines[index].startswith("@@ "):
            if not lines[index].startswith(("--- ", "+++ ")):
                hunk.append(lines[index])
            index += 1

        current_section = section_by_line.get(max(1, new_start), section)
        current_line = max(1, new_start)
        section_hunks = {}
        for diff_line in hunk[1:]:
            prefix = diff_line[:1]
            content = diff_line[1:] if prefix in (" ", "+", "-") else diff_line
            if prefix in (" ", "+"):
                current_section = section_by_line.get(current_line, current_section)
                current_line += 1
            elif prefix == "-" and content.lstrip().startswith("["):
                try:
                    old_path, old_array = header_path(content)
                except (tomlkit.exceptions.TOMLKitError, ValueError):
                    old_path, old_array = (), False
                if old_path:
                    current_section = "Removed " + (
                        ("[[" if old_array else "[") + ".".join(map(str, old_path))
                        + ("]]" if old_array else "]")
                    )
            section_hunks.setdefault(current_section, []).append(diff_line)
        for name, section_lines in section_hunks.items():
            groups.setdefault(name, []).extend([hunk[0], *section_lines, "\n"])
    return groups
