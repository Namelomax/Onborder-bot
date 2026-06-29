"""Конфигурация этапов онбординга и чек-листов (ТЗ: сопровождение по этапам)."""

# Этапы онбординга. doc — ключ документа базы знаний, привязанного к этапу.
STAGES = [
    {
        "id": 0,
        "title": "Знакомство с организацией",
        "doc": "01_welcome.md",
        "checklist": [
            ("welcome_read", "Прочитать приветственный материал"),
            ("welcome_role", "Понять роль тренера в центре"),
        ],
    },
    {
        "id": 1,
        "title": "Изучение методики",
        "doc": "02_methodology.md",
        "checklist": [
            ("method_read", "Изучить методику проведения занятий"),
            ("method_lesson", "Разобрать структуру типового занятия"),
        ],
    },
    {
        "id": 2,
        "title": "Техника безопасности",
        "doc": "03_safety.md",
        "checklist": [
            ("safety_read", "Ознакомиться с правилами ТБ"),
            ("safety_rules", "Запомнить действия в нештатной ситуации"),
        ],
    },
    {
        "id": 3,
        "title": "Инструменты и сервисы",
        "doc": "04_tools.md",
        "checklist": [
            ("tools_read", "Изучить инструменты тренера"),
            ("tools_access", "Запросить доступы у администратора"),
        ],
    },
]


def get_stage(stage_id: int) -> dict | None:
    for stage in STAGES:
        if stage["id"] == stage_id:
            return stage
    return None


def total_stages() -> int:
    return len(STAGES)
