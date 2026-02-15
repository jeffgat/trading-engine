#!/usr/bin/env python3
"""Scaffold a new skill directory with the required structure and templates."""

import argparse
import re
import sys
import textwrap
from pathlib import Path

FORBIDDEN_WORDS = {"claude", "anthropic"}
KEBAB_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


def validate_name(name: str) -> list[str]:
    """Return a list of validation error messages (empty if valid)."""
    errors = []
    if not KEBAB_CASE_RE.match(name):
        errors.append(
            f"Name '{name}' is not valid kebab-case. "
            "Use only lowercase letters, numbers, and hyphens (e.g. 'my-skill')."
        )
    for word in FORBIDDEN_WORDS:
        if word in name.lower():
            errors.append(f"Name must not contain the word '{word}'.")
    return errors


def skill_md_template(name: str) -> str:
    """Return the SKILL.md template content."""
    title = name.replace("-", " ").title()
    return textwrap.dedent(f"""\
        ---
        name: {name}
        description: >
          TODO: Describe what this skill does. This skill should be used when
          [describe trigger conditions]. Key capabilities include [list capabilities].
        ---

        # {title}

        TODO: Write a 1-2 sentence purpose statement.

        ## When to Use

        This skill should be activated when:

        - TODO: Describe the primary trigger condition
        - TODO: Describe secondary trigger conditions

        ## Do NOT Use When

        - TODO: Describe out-of-scope requests
        - TODO: Describe adjacent tasks handled by other skills

        ## Workflow

        ### Step 1: Gather Context

        TODO: Describe how to gather the necessary information from the user or environment.

        ### Step 2: Execute

        TODO: Describe the main execution steps.

        - Run `scripts/example.py` to [accomplish task]
        - Load `references/example.md` for [specific guidance]

        ### Step 3: Deliver Output

        TODO: Describe how to present results to the user.

        ## Error Handling

        | Error | Recovery |
        |-------|----------|
        | TODO: Common error 1 | TODO: How to recover |
        | TODO: Common error 2 | TODO: How to recover |
    """)


def example_script(name: str) -> str:
    """Return the example script content."""
    return textwrap.dedent(f"""\
        #!/usr/bin/env python3
        \"\"\"Example script for the {name} skill.

        Replace this with a real script or delete if not needed.
        \"\"\"

        import sys


        def main() -> None:
            print(f"Hello from {name}!")
            print(f"Arguments: {{sys.argv[1:]}}")


        if __name__ == "__main__":
            main()
    """)


def example_reference(name: str) -> str:
    """Return the example reference content."""
    title = name.replace("-", " ").title()
    return textwrap.dedent(f"""\
        # {title} Reference

        This is an example reference file. Replace with actual reference content
        or delete if not needed.

        ## Section 1

        TODO: Add reference material here.
    """)


def create_skill(name: str, output_dir: Path) -> None:
    """Create the skill directory structure."""
    skill_dir = output_dir / name

    if skill_dir.exists():
        print(f"\033[31mError:\033[0m Directory already exists: {skill_dir}")
        sys.exit(1)

    # Create directories
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "assets").mkdir(parents=True)

    # Create files
    (skill_dir / "SKILL.md").write_text(skill_md_template(name))
    (skill_dir / "scripts" / "example.py").write_text(example_script(name))
    (skill_dir / "references" / "example.md").write_text(example_reference(name))
    (skill_dir / "assets" / ".gitkeep").write_text("")

    # Make example script executable
    (skill_dir / "scripts" / "example.py").chmod(0o755)

    print(f"\033[32mSuccess!\033[0m Skill '{name}' created at: {skill_dir}")
    print()
    print("Created structure:")
    print(f"  {name}/")
    print(f"  ├── SKILL.md              (edit frontmatter and instructions)")
    print(f"  ├── scripts/")
    print(f"  │   └── example.py        (replace or delete)")
    print(f"  ├── references/")
    print(f"  │   └── example.md        (replace or delete)")
    print(f"  └── assets/")
    print(f"      └── .gitkeep          (add output assets here)")
    print()
    print("Next steps:")
    print("  1. Edit SKILL.md — fill in the TODO placeholders")
    print("  2. Add scripts, references, and assets as needed")
    print("  3. Delete example files that aren't needed")
    print("  4. Run package_skill.py to validate and package")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scaffold a new skill directory.",
        epilog="Example: python3 init_skill.py my-skill --path ./skills",
    )
    parser.add_argument(
        "name",
        help="Skill name in kebab-case (e.g. 'pdf-editor')",
    )
    parser.add_argument(
        "--path",
        default=".",
        help="Parent directory for the new skill folder (default: current directory)",
    )
    args = parser.parse_args()

    # Validate name
    errors = validate_name(args.name)
    if errors:
        for err in errors:
            print(f"\033[31mError:\033[0m {err}")
        sys.exit(1)

    # Validate output directory
    output_dir = Path(args.path)
    if not output_dir.exists():
        print(f"\033[31mError:\033[0m Parent directory does not exist: {output_dir}")
        sys.exit(1)

    create_skill(args.name, output_dir)


if __name__ == "__main__":
    main()
