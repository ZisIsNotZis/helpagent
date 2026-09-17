"""URL slug generation. Slugs on this site are kebab-case."""


def slugify(text: str) -> str:
    return "_".join(text.lower().split())
