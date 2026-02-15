#!/usr/bin/env python3
"""Validate and package a skill folder into a distributable zip file."""

import argparse
import os
import re
import sys
import zipfile
from pathlib import Path

KEBAB_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
FORBIDDEN_WORDS = {"claude", "anthropic"}
HIDDEN_PATTERNS = {".git", ".DS_Store", ".env", "__pycache__", ".pyc"}

# ANSI colors
RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
BOLD = "\033[1m"
RESET = "\033[0m"


def parse_frontmatter(content: str) -> dict[str, str] | None:
    """Parse YAML frontmatter from SKILL.md content.

    Uses simple key-value extraction. Falls back to hand-rolled parsing
    if the yaml module is not available.
    """
    lines = content.split("\n")

    # Find frontmatter delimiters
    if not lines or lines[0].strip() != "---":
        return None

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return None

    frontmatter_lines = lines[1:end_idx]

    # Try yaml module first
    try:
        import yaml
        return yaml.safe_load("\n".join(frontmatter_lines)) or {}
    except ImportError:
        pass

    # Hand-rolled parsing for simple key: value pairs
    result = {}
    current_key = None
    current_value_lines = []

    for line in frontmatter_lines:
        # Skip empty lines and comments
        if not line.strip() or line.strip().startswith("#"):
            if current_key:
                current_value_lines.append("")
            continue

        # Check for key: value pattern (not indented)
        if not line.startswith((" ", "\t")) and ":" in line:
            # Save previous key
            if current_key:
                result[current_key] = " ".join(
                    l.strip() for l in current_value_lines if l.strip()
                ).strip()

            key, _, value = line.partition(":")
            current_key = key.strip()
            value = value.strip()

            # Handle multi-line indicator
            if value == ">" or value == "|":
                current_value_lines = []
            else:
                current_value_lines = [value]
        elif current_key:
            current_value_lines.append(line)

    # Save last key
    if current_key:
        result[current_key] = " ".join(
            l.strip() for l in current_value_lines if l.strip()
        ).strip()

    return result


def count_words(content: str) -> int:
    """Count words in the markdown body (excluding frontmatter)."""
    lines = content.split("\n")

    # Skip frontmatter
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                lines = lines[i + 1:]
                break

    return len(" ".join(lines).split())


def validate_skill(skill_dir: Path) -> tuple[list[str], list[str]]:
    """Validate a skill directory. Returns (errors, warnings)."""
    errors = []
    warnings = []

    # --- ERROR checks ---

    # Check SKILL.md exists with exact casing
    skill_md = skill_dir / "SKILL.md"
    has_skill_md = False

    for f in skill_dir.iterdir():
        if f.name.lower() == "skill.md":
            if f.name == "SKILL.md":
                has_skill_md = True
            else:
                errors.append(
                    f"Found '{f.name}' but file must be named exactly 'SKILL.md' (case-sensitive)"
                )

    if not has_skill_md and not any(
        e.startswith("Found '") for e in errors
    ):
        errors.append("SKILL.md not found in skill directory")

    if not has_skill_md:
        return errors, warnings

    content = skill_md.read_text()

    # Check frontmatter exists
    frontmatter = parse_frontmatter(content)
    if frontmatter is None:
        errors.append(
            "YAML frontmatter not found. SKILL.md must start with '---' delimiters"
        )
        return errors, warnings

    # Check 'name' field
    name = frontmatter.get("name", "")
    if not name:
        errors.append("Required field 'name' is missing from frontmatter")
    else:
        if not KEBAB_CASE_RE.match(str(name)):
            errors.append(
                f"Name '{name}' is not valid kebab-case "
                "(use only lowercase letters, numbers, and hyphens)"
            )
        for word in FORBIDDEN_WORDS:
            if word in str(name).lower():
                errors.append(f"Name must not contain the forbidden word '{word}'")

    # Check 'description' field
    description = frontmatter.get("description", "")
    if not description:
        errors.append("Required field 'description' is missing from frontmatter")
    else:
        desc_str = str(description)
        if "<" in desc_str or ">" in desc_str:
            errors.append("Description must not contain XML angle brackets (< or >)")

    # Check folder name is kebab-case
    folder_name = skill_dir.name
    if not KEBAB_CASE_RE.match(folder_name):
        errors.append(
            f"Folder name '{folder_name}' is not valid kebab-case "
            "(use only lowercase letters, numbers, and hyphens)"
        )

    # --- WARNING checks ---

    if name and folder_name != str(name):
        warnings.append(
            f"Folder name '{folder_name}' does not match frontmatter name '{name}'"
        )

    if description:
        desc_str = str(description)
        if len(desc_str) > 1024:
            warnings.append(
                f"Description is {len(desc_str)} characters (recommended: under 1024)"
            )

        # Check description quality
        desc_lower = desc_str.lower()
        has_what = len(desc_str) > 20  # Minimal "what" check
        has_when = any(
            phrase in desc_lower
            for phrase in [
                "should be used when",
                "use this when",
                "use when",
                "invokes",
                "asks to",
                "wants to",
            ]
        )
        if not has_when:
            warnings.append(
                "Description may be missing trigger conditions "
                "(include 'should be used when' or similar phrasing)"
            )
        if not has_what:
            warnings.append("Description appears too short to convey skill purpose")

    # Check SKILL.md word count
    word_count = count_words(content)
    if word_count > 5000:
        warnings.append(
            f"SKILL.md body is {word_count} words (recommended: under 5000). "
            "Consider moving detailed content to references/"
        )

    # Check compatibility length
    compat = frontmatter.get("compatibility", "")
    if compat and len(str(compat)) > 200:
        warnings.append("Compatibility field is unusually long")

    # Check for README.md
    if (skill_dir / "README.md").exists():
        warnings.append(
            "Found README.md in skill folder. SKILL.md serves as the readme; "
            "consider removing README.md"
        )

    return errors, warnings


def package_skill(skill_dir: Path, output_dir: Path) -> Path | None:
    """Create a zip file for the skill. Returns the zip path or None on error."""
    skill_name = skill_dir.name
    zip_path = output_dir / f"{skill_name}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(skill_dir):
            # Filter hidden directories
            dirs[:] = [
                d for d in dirs
                if not any(d.startswith(p) or d == p for p in HIDDEN_PATTERNS)
            ]

            for file in files:
                # Skip hidden files
                if any(file.startswith(p) or file == p for p in HIDDEN_PATTERNS):
                    continue
                if file.endswith(".pyc"):
                    continue

                file_path = Path(root) / file
                arcname = file_path.relative_to(skill_dir.parent)
                zf.write(file_path, arcname)

    return zip_path


def print_results(
    errors: list[str], warnings: list[str], skill_dir: Path
) -> None:
    """Print validation results with color coding."""
    print(f"\n{BOLD}Validating skill: {skill_dir.name}{RESET}\n")

    if errors:
        print(f"{RED}{BOLD}ERRORS ({len(errors)}):{RESET}")
        for err in errors:
            print(f"  {RED}✗{RESET} {err}")
        print()

    if warnings:
        print(f"{YELLOW}{BOLD}WARNINGS ({len(warnings)}):{RESET}")
        for warn in warnings:
            print(f"  {YELLOW}!{RESET} {warn}")
        print()

    if not errors and not warnings:
        print(f"  {GREEN}✓ All checks passed{RESET}\n")
    elif not errors:
        print(f"  {GREEN}✓ No errors (warnings are non-blocking){RESET}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and package a skill into a zip file.",
        epilog="Example: python3 package_skill.py ./my-skill --output ./dist",
    )
    parser.add_argument(
        "skill_folder",
        help="Path to the skill directory",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory for the zip file (default: current directory)",
    )
    args = parser.parse_args()

    skill_dir = Path(args.skill_folder).resolve()

    if not skill_dir.is_dir():
        print(f"{RED}Error:{RESET} Not a directory: {skill_dir}")
        sys.exit(1)

    # Validate
    errors, warnings = validate_skill(skill_dir)
    print_results(errors, warnings, skill_dir)

    if errors:
        print(f"{RED}Packaging aborted due to errors.{RESET}")
        sys.exit(1)

    # Package
    output_dir = Path(args.output).resolve() if args.output else Path.cwd()
    if not output_dir.exists():
        output_dir.mkdir(parents=True)

    zip_path = package_skill(skill_dir, output_dir)
    if zip_path:
        size_kb = zip_path.stat().st_size / 1024
        print(f"{GREEN}{BOLD}Packaged:{RESET} {zip_path} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
