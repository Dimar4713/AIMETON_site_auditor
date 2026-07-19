from __future__ import annotations

"""Каталог разрешённых источников для экономической разведки.

Источник описывается отдельно от адаптера доступа. Наличие записи не означает,
что сайт разрешено автоматически обходить. Перед подключением адаптера должны
быть проверены API, robots.txt, условия использования и допустимая нагрузка.
"""

HUNTER_SOURCES = [
    {
        "id": "marketmap_firms",
        "name": "MarketMap — справочник компаний",
        "base_url": "https://firms.marketmap.ru",
        "coverage": "Россия",
        "source_type": "business_directory",
        "use_for": ["название компании", "отрасль", "регион", "сайт компании"],
        "access_mode": "search_discovery_only",
        "priority": 70,
        "notes": "Использовать как источник обнаружения. Автоматический обход — только после проверки условий доступа.",
    },
    {
        "id": "kompass",
        "name": "Kompass",
        "base_url": "https://www.kompass.com",
        "coverage": "международный B2B",
        "source_type": "b2b_directory",
        "use_for": ["отраслевая классификация", "B2B-компании", "международное расширение"],
        "access_mode": "licensed_or_api_preferred",
        "priority": 60,
        "notes": "Предпочтителен официальный API или лицензированный экспорт.",
    },
    {
        "id": "rbc_companies",
        "name": "РБК Компании",
        "base_url": "https://companies.rbc.ru",
        "coverage": "Россия",
        "source_type": "company_directory",
        "use_for": ["категории деятельности", "юридическая идентификация", "регион"],
        "access_mode": "search_discovery_only",
        "priority": 75,
        "notes": "Использовать для подтверждения профиля и категории компании.",
    },
    {
        "id": "rusprofile",
        "name": "Rusprofile",
        "base_url": "https://www.rusprofile.ru",
        "coverage": "Россия",
        "source_type": "legal_entity_registry_aggregator",
        "use_for": ["ОКВЭД", "юридический статус", "руководитель", "финансовые признаки", "регион"],
        "access_mode": "manual_or_licensed",
        "priority": 90,
        "notes": "Сильный источник квалификации, но не считать автоматически разрешённым для массового парсинга.",
    },
    {
        "id": "star_pro",
        "name": "СТАР — система торговых аналитических решений",
        "base_url": "https://star-pro.ru",
        "coverage": "Россия",
        "source_type": "counterparty_analytics",
        "use_for": ["ОКВЭД", "ОКАТО", "финансовая отчётность", "контакты"],
        "access_mode": "manual_or_licensed",
        "priority": 65,
        "notes": "Применять для дополнительного подтверждения коммерческой состоятельности.",
    },
    {
        "id": "spravochnik24",
        "name": "Справочник24.онлайн",
        "base_url": "https://справочник24.онлайн",
        "coverage": "Россия",
        "source_type": "business_directory",
        "use_for": ["название", "телефон", "адрес", "сфера деятельности", "сайт"],
        "access_mode": "search_discovery_only",
        "priority": 65,
        "notes": "Полезен для регионального охвата и восстановления отсутствующих сайтов.",
    },
    {
        "id": "general_search",
        "name": "Общий веб-поиск через SearXNG",
        "base_url": None,
        "coverage": "зависит от подключённых поисковых систем",
        "source_type": "metasearch",
        "use_for": ["обнаружение официальных сайтов", "поиск отраслевых каталогов", "проверка цифрового присутствия"],
        "access_mode": "api",
        "priority": 100,
        "notes": "Основной универсальный канал; далее данные подтверждаются несколькими источниками.",
    },
]


def get_hunter_sources() -> dict:
    return {
        "version": "0.1.0",
        "principle": "несколько независимых источников для обнаружения и подтверждения цели",
        "sources": HUNTER_SOURCES,
        "rules": [
            "не считать поисковую выдачу доказательством факта",
            "подтверждать регион и профиль минимум по двум независимым признакам",
            "не выполнять массовый обход источника без разрешённого API или проверки условий использования",
            "официальный сайт компании является основным объектом глубокой проработки",
            "юридические и финансовые сведения использовать только как квалифицирующие признаки",
        ],
    }
