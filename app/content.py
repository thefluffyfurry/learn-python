"""Lesson generation for the Python teaching app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class QuizQuestion:
    prompt: str
    options: List[str]
    answer_index: int
    explanation: str


@dataclass(frozen=True)
class Lesson:
    lesson_id: str
    topic_slug: str
    topic_name: str
    stage: int
    title: str
    summary: str
    explanation: str
    code_sample: str
    challenge: str
    xp_reward: int
    quiz: QuizQuestion


TOPICS = [
    {
        "slug": "syntax",
        "name": "Python Basics",
        "focus": "core Python syntax, variables, and script structure",
        "snippet": "name = 'Ada'\nlevel = 1\nprint(name, level)",
        "concept": "basic script execution",
    },
    {
        "slug": "strings",
        "name": "Strings",
        "focus": "text handling, formatting, and string methods",
        "snippet": "user = 'Sam'\nprint(user.upper())\nprint(f'Hello {user}')",
        "concept": "string operations",
    },
    {
        "slug": "numbers",
        "name": "Numbers",
        "focus": "integers, floats, arithmetic, and numeric reasoning",
        "snippet": "total = 7 + 5\naverage = total / 2\nprint(total, average)",
        "concept": "numeric expressions",
    },
    {
        "slug": "conditionals",
        "name": "Conditionals",
        "focus": "branching with if, elif, else, and comparison logic",
        "snippet": "score = 84\nif score >= 80:\n    print('pass')\nelse:\n    print('retry')",
        "concept": "conditional branching",
    },
    {
        "slug": "loops",
        "name": "Loops",
        "focus": "repetition with for, while, ranges, and loop control",
        "snippet": "for step in range(3):\n    print('step', step)",
        "concept": "repetition",
    },
    {
        "slug": "lists",
        "name": "Lists",
        "focus": "ordered collections, indexing, slicing, and mutation",
        "snippet": "items = ['pen', 'book']\nitems.append('lamp')\nprint(items[0], items[-1])",
        "concept": "sequence handling",
    },
    {
        "slug": "dicts",
        "name": "Dictionaries",
        "focus": "key-value mappings, lookups, updates, and iteration",
        "snippet": "player = {'name': 'Kai', 'xp': 20}\nplayer['xp'] += 5\nprint(player)",
        "concept": "mapping data",
    },
    {
        "slug": "functions",
        "name": "Functions",
        "focus": "def, parameters, return values, and reusable logic",
        "snippet": "def greet(name):\n    return f'Hello {name}'\n\nprint(greet('Mina'))",
        "concept": "function design",
    },
    {
        "slug": "modules",
        "name": "Modules",
        "focus": "imports, namespaces, and code organization",
        "snippet": "import math\nprint(math.sqrt(49))",
        "concept": "using modules",
    },
    {
        "slug": "files",
        "name": "Files",
        "focus": "reading, writing, and managing file resources safely",
        "snippet": "with open('notes.txt', 'w', encoding='utf-8') as handle:\n    handle.write('practice')",
        "concept": "file operations",
    },
    {
        "slug": "oop",
        "name": "Object-Oriented Python",
        "focus": "classes, instances, methods, and object state",
        "snippet": "class Pet:\n    def __init__(self, name):\n        self.name = name\n\nprint(Pet('Luna').name)",
        "concept": "class modeling",
    },
    {
        "slug": "debugging",
        "name": "Debugging",
        "focus": "tracing values, reading errors, and isolating bugs",
        "snippet": "value = '5'\nprint(type(value))",
        "concept": "debugging workflow",
    },
]

STAGE_BLUEPRINTS = [
    ("Foundations", "learn the shape of the concept and how to recognize it"),
    ("Practice", "apply the idea in a short script with predictable outputs"),
    ("Reasoning", "trace what the code does and explain why it works"),
    ("Variation", "modify the pattern to support slightly different input"),
    ("Common Mistakes", "spot the bug or misconception before it spreads"),
    ("Mini Project", "combine the concept with previous lessons to build something"),
    ("Fluency", "read code faster and identify the cleanest solution"),
    ("Mastery Check", "answer a scenario-based question with confidence"),
]


def _build_quiz(topic_name: str, concept: str, stage_label: str, stage: int) -> QuizQuestion:
    prompt = f"Which option best demonstrates {concept} during the {stage_label.lower()} stage?"
    options = [
        f"Use Python code that clearly applies {concept} to produce a result.",
        "Avoid code entirely and only describe the idea in plain English.",
        "Use random syntax from another language and expect Python to accept it.",
        "Ignore the result and focus only on file names.",
    ]
    answer_index = 0
    explanation = (
        f"In {topic_name}, the goal is to practice {concept} with valid Python code. "
        "The correct answer is the only option that actually applies the concept."
    )
    if stage % 3 == 0:
        prompt = f"What is the strongest habit for improving at {topic_name.lower()}?"
        options = [
            "Run small examples, read the output, and adjust one change at a time.",
            "Memorize keywords without testing them.",
            "Skip errors and assume the program is still correct.",
            "Rewrite everything before understanding the first bug.",
        ]
        explanation = (
            "Strong Python learning comes from tight feedback loops: write a small example, run it, "
            "and inspect the behavior before moving on."
        )
    return QuizQuestion(
        prompt=prompt,
        options=options,
        answer_index=answer_index,
        explanation=explanation,
    )


def generate_lessons() -> List[Lesson]:
    lessons: List[Lesson] = []
    for topic in TOPICS:
        for stage in range(1, 26):
            stage_label, stage_goal = STAGE_BLUEPRINTS[(stage - 1) % len(STAGE_BLUEPRINTS)]
            xp_reward = 10 + stage * 2
            title = f"{topic['name']} {stage:02d}: {stage_label}"
            summary = (
                f"Stage {stage} of {topic['name']} focuses on {topic['focus']} and helps you {stage_goal}."
            )
            explanation = (
                f"This lesson teaches {topic['focus']}. At this stage you should concentrate on "
                f"{topic['concept']} and learn to explain each line before you run it. "
                f"Work through the sample, predict the output, then change one value and run it again."
            )
            code_sample = (
                f"# {topic['name']} lesson {stage}\n"
                f"{topic['snippet']}\n"
                f"print('Stage', {stage})"
            )
            challenge = (
                f"Edit the example so it better demonstrates {topic['concept']}. "
                f"Then describe what changed and why that matters in stage {stage}."
            )
            lesson_id = f"{topic['slug']}-{stage:02d}"
            lessons.append(
                Lesson(
                    lesson_id=lesson_id,
                    topic_slug=topic["slug"],
                    topic_name=topic["name"],
                    stage=stage,
                    title=title,
                    summary=summary,
                    explanation=explanation,
                    code_sample=code_sample,
                    challenge=challenge,
                    xp_reward=xp_reward,
                    quiz=_build_quiz(topic["name"], topic["concept"], stage_label, stage),
                )
            )
    return lessons


LESSONS = generate_lessons()
LESSON_MAP: Dict[str, Lesson] = {lesson.lesson_id: lesson for lesson in LESSONS}


def topic_progress_groups() -> Dict[str, List[Lesson]]:
    grouped: Dict[str, List[Lesson]] = {}
    for lesson in LESSONS:
        grouped.setdefault(lesson.topic_name, []).append(lesson)
    return grouped
