"""Skill normalization and synonym mapping."""
from __future__ import annotations

SYNONYMS: dict[str, list[str]] = {
    "python": ["python3", "py", "cpython"],
    "javascript": ["js", "ecmascript", "es6", "es2015+"],
    "typescript": ["ts"],
    "react": ["reactjs", "react.js"],
    "vue": ["vuejs", "vue.js"],
    "angular": ["angularjs"],
    "node": ["nodejs", "node.js"],
    "go": ["golang"],
    "rust": ["rust-lang"],
    "kubernetes": ["k8s"],
    "docker": ["containers", "containerization"],
    "aws": ["amazon web services"],
    "gcp": ["google cloud", "google cloud platform"],
    "azure": ["microsoft azure"],
    "postgresql": ["postgres", "psql"],
    "mongodb": ["mongo"],
    "redis": ["redis-server"],
    "graphql": ["gql"],
    "rest": ["restful", "rest api"],
    "ci/cd": ["cicd", "continuous integration", "continuous deployment"],
    "machine learning": ["ml"],
    "deep learning": ["dl"],
    "artificial intelligence": ["ai"],
    "natural language processing": ["nlp"],
    "terraform": ["tf"],
}

_reverse_map: dict[str, str] = {}
for canonical, aliases in SYNONYMS.items():
    _reverse_map[canonical] = canonical
    for alias in aliases:
        _reverse_map[alias.lower()] = canonical

class SkillsTaxonomy:
    def normalize(self, skill: str) -> str:
        return _reverse_map.get(skill.lower().strip(), skill.lower().strip())

    def match_score(self, candidate_skills: list[str], required_skills: list[str]) -> float:
        if not required_skills:
            return 1.0
        normalized_candidate = {self.normalize(s) for s in candidate_skills}
        normalized_required = {self.normalize(s) for s in required_skills}
        matched = normalized_candidate & normalized_required
        return len(matched) / len(normalized_required) if normalized_required else 1.0
