"""
Skills Package: SKILL.md files for deepagents progressive disclosure.

Skills are organized by domain in subdirectories:
    skills/
    +-- technical/     (trend-detection, fibonacci-analysis, momentum-signals)
    +-- financial/     (valuation-assessment, cashflow-health, earnings-quality)
    +-- news/          (sentiment-analysis, catalyst-identification, market-mood)
    +-- debater/       (fact-checking, counter-evidence, risk-assessment, assumption-testing)

Each skill folder contains a SKILL.md with YAML frontmatter metadata
and a markdown body with detailed workflow instructions. The deepagents
SkillsMiddleware loads frontmatter into the system prompt and provides
on-demand read_file access to full skill content.

Note: The old Skill dataclass, SkillRegistry, and *_skills.py factory
files have been replaced by the SKILL.md standard + deepagents library.
"""
