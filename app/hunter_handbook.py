from __future__ import annotations

"""Справочник охотника AIMETON.

Каталог задаёт пространство поиска, а не жёсткий сценарий. Агент использует его
для построения запросов, классификации бизнеса, распознавания экономических
сигналов и выбора подходящего AI-продукта.
"""

BUSINESS_MODELS = {
    "b2c_retail": "B2C-розница и интернет-магазин",
    "b2b_distribution": "B2B-дистрибуция и оптовые поставки",
    "manufacturing": "Производство",
    "project_sales": "Проектные продажи",
    "services": "Услуги",
    "subscription": "Подписочная модель",
    "marketplace": "Маркетплейс или агрегатор",
    "rental": "Аренда и прокат",
    "franchise": "Франчайзинг",
    "public_sector": "Государственные и муниципальные услуги",
}

OPPORTUNITY_PATTERNS = {
    "complex_choice": "сложный выбор товара или услуги",
    "compatibility": "проверка совместимости и комплектации",
    "repetitive_questions": "много повторяющихся консультаций",
    "lead_qualification": "слабая квалификация входящих заявок",
    "slow_quote": "долгая подготовка расчёта или коммерческого предложения",
    "after_hours": "потеря обращений вне рабочего времени",
    "knowledge_fragmentation": "знания рассеяны по документам и сотрудникам",
    "large_catalog": "большой и неоднородный каталог",
    "appointment_load": "ручная запись и распределение клиентов",
    "document_routine": "высокая доля документной рутины",
    "support_load": "перегрузка первой линии поддержки",
    "content_quality": "неполные или несогласованные карточки и описания",
    "repeat_sales": "слабая работа с повторными продажами",
    "claims": "много претензий, возвратов или спорных обращений",
}

AI_PRODUCTS = {
    "selection_consultant": "AI-консультант по подбору",
    "compatibility_agent": "Агент совместимости и комплектации",
    "lead_qualifier": "AI-квалификатор лидов",
    "quote_generator": "Генератор расчётов и коммерческих предложений",
    "knowledge_assistant": "AI-справочник по документам и знаниям",
    "support_agent": "AI-первая линия поддержки",
    "booking_agent": "AI-агент записи и маршрутизации",
    "catalog_controller": "Агент контроля каталога и контента",
    "sales_assistant": "AI-помощник менеджера по продажам",
    "claims_agent": "Агент обработки претензий",
    "document_agent": "Агент подготовки и проверки документов",
    "monitoring_agent": "Агент мониторинга и выявления отклонений",
}

INDUSTRIES = [
    {
        "id": "hvac",
        "name": "Отопление, вентиляция и кондиционирование",
        "aliases": ["отопление", "вентиляция", "кондиционеры", "котлы", "климатическое оборудование"],
        "business_models": ["b2c_retail", "b2b_distribution", "project_sales", "services"],
        "signals": ["complex_choice", "compatibility", "slow_quote", "after_hours"],
        "products": ["selection_consultant", "compatibility_agent", "quote_generator", "lead_qualifier"],
    },
    {
        "id": "construction_materials",
        "name": "Строительные и отделочные материалы",
        "aliases": ["стройматериалы", "кровля", "фасады", "утеплитель", "сухие смеси", "пиломатериалы"],
        "business_models": ["b2c_retail", "b2b_distribution", "manufacturing"],
        "signals": ["large_catalog", "complex_choice", "compatibility", "slow_quote"],
        "products": ["selection_consultant", "compatibility_agent", "quote_generator", "catalog_controller"],
    },
    {
        "id": "industrial_equipment",
        "name": "Промышленное оборудование и комплектующие",
        "aliases": ["станки", "насосы", "компрессоры", "электродвигатели", "КИПиА", "промышленное оборудование"],
        "business_models": ["b2b_distribution", "manufacturing", "project_sales"],
        "signals": ["complex_choice", "compatibility", "slow_quote", "knowledge_fragmentation"],
        "products": ["selection_consultant", "compatibility_agent", "quote_generator", "knowledge_assistant"],
    },
    {
        "id": "automotive",
        "name": "Автомобили, автозапчасти и автосервис",
        "aliases": ["автозапчасти", "автосервис", "шины", "масла", "ремонт автомобилей", "автосалон"],
        "business_models": ["b2c_retail", "b2b_distribution", "services"],
        "signals": ["compatibility", "large_catalog", "appointment_load", "repetitive_questions"],
        "products": ["compatibility_agent", "selection_consultant", "booking_agent", "support_agent"],
    },
    {
        "id": "furniture",
        "name": "Мебель, кухни и интерьерные решения",
        "aliases": ["мебель", "кухни", "шкафы", "дизайн интерьера", "мебель на заказ"],
        "business_models": ["b2c_retail", "manufacturing", "project_sales"],
        "signals": ["complex_choice", "lead_qualification", "slow_quote", "after_hours"],
        "products": ["selection_consultant", "lead_qualifier", "quote_generator", "sales_assistant"],
    },
    {
        "id": "windows_doors",
        "name": "Окна, двери, фасады и кровля",
        "aliases": ["окна ПВХ", "двери", "фасады", "ворота", "кровля"],
        "business_models": ["manufacturing", "project_sales", "services"],
        "signals": ["slow_quote", "lead_qualification", "complex_choice"],
        "products": ["quote_generator", "lead_qualifier", "selection_consultant"],
    },
    {
        "id": "healthcare",
        "name": "Медицинские центры и стоматология",
        "aliases": ["стоматология", "клиника", "медицинский центр", "диагностика", "косметология"],
        "business_models": ["services"],
        "signals": ["appointment_load", "repetitive_questions", "after_hours", "support_load"],
        "products": ["booking_agent", "support_agent", "lead_qualifier", "knowledge_assistant"],
    },
    {
        "id": "real_estate",
        "name": "Недвижимость и загородное строительство",
        "aliases": ["недвижимость", "новостройки", "коттеджи", "строительство домов", "риэлтор"],
        "business_models": ["project_sales", "services"],
        "signals": ["lead_qualification", "complex_choice", "after_hours", "slow_quote"],
        "products": ["lead_qualifier", "selection_consultant", "sales_assistant", "quote_generator"],
    },
    {
        "id": "education",
        "name": "Образование и профессиональное обучение",
        "aliases": ["учебный центр", "курсы", "школа", "повышение квалификации", "онлайн-обучение"],
        "business_models": ["services", "subscription"],
        "signals": ["complex_choice", "lead_qualification", "repetitive_questions", "after_hours"],
        "products": ["selection_consultant", "lead_qualifier", "support_agent", "booking_agent"],
    },
    {
        "id": "tourism",
        "name": "Туризм, гостиницы и базы отдыха",
        "aliases": ["туризм", "гостиница", "отель", "база отдыха", "туры", "экскурсии"],
        "business_models": ["services", "rental"],
        "signals": ["appointment_load", "after_hours", "complex_choice", "repetitive_questions"],
        "products": ["booking_agent", "selection_consultant", "support_agent", "sales_assistant"],
    },
    {
        "id": "logistics",
        "name": "Логистика, доставка и складские услуги",
        "aliases": ["логистика", "доставка", "грузоперевозки", "склад", "курьерская служба"],
        "business_models": ["services", "b2b_distribution"],
        "signals": ["support_load", "repetitive_questions", "claims", "document_routine"],
        "products": ["support_agent", "claims_agent", "document_agent", "monitoring_agent"],
    },
    {
        "id": "it_cloud",
        "name": "IT, облачная инфраструктура и хостинг",
        "aliases": ["IT-компания", "облако", "VPS", "хостинг", "интегратор", "разработка ПО"],
        "business_models": ["services", "subscription", "project_sales"],
        "signals": ["support_load", "knowledge_fragmentation", "slow_quote", "lead_qualification"],
        "products": ["support_agent", "knowledge_assistant", "quote_generator", "lead_qualifier"],
    },
    {
        "id": "legal_accounting",
        "name": "Юридические, бухгалтерские и консалтинговые услуги",
        "aliases": ["юридические услуги", "бухгалтерия", "консалтинг", "аудит", "налоговый консультант"],
        "business_models": ["services"],
        "signals": ["lead_qualification", "document_routine", "knowledge_fragmentation", "slow_quote"],
        "products": ["lead_qualifier", "document_agent", "knowledge_assistant", "quote_generator"],
    },
    {
        "id": "food_horeca",
        "name": "Пищевая отрасль, рестораны и общественное питание",
        "aliases": ["ресторан", "кафе", "доставка еды", "производство продуктов", "кейтеринг"],
        "business_models": ["b2c_retail", "manufacturing", "services"],
        "signals": ["appointment_load", "after_hours", "support_load", "content_quality"],
        "products": ["booking_agent", "support_agent", "catalog_controller", "sales_assistant"],
    },
    {
        "id": "beauty_fitness",
        "name": "Красота, фитнес и персональные услуги",
        "aliases": ["салон красоты", "фитнес", "барбершоп", "SPA", "массаж"],
        "business_models": ["services", "subscription"],
        "signals": ["appointment_load", "after_hours", "repeat_sales", "repetitive_questions"],
        "products": ["booking_agent", "support_agent", "sales_assistant", "lead_qualifier"],
    },
    {
        "id": "agriculture",
        "name": "Сельское хозяйство и агроснабжение",
        "aliases": ["агроснабжение", "семена", "удобрения", "сельхозтехника", "фермерское хозяйство"],
        "business_models": ["b2b_distribution", "manufacturing", "project_sales"],
        "signals": ["complex_choice", "compatibility", "slow_quote", "knowledge_fragmentation"],
        "products": ["selection_consultant", "compatibility_agent", "quote_generator", "knowledge_assistant"],
    },
    {
        "id": "energy_electrical",
        "name": "Энергетика и электротехническая продукция",
        "aliases": ["электротехника", "кабель", "электрооборудование", "энергетика", "освещение"],
        "business_models": ["b2b_distribution", "manufacturing", "project_sales"],
        "signals": ["large_catalog", "compatibility", "slow_quote", "complex_choice"],
        "products": ["compatibility_agent", "selection_consultant", "quote_generator", "catalog_controller"],
    },
    {
        "id": "security",
        "name": "Безопасность, видеонаблюдение и контроль доступа",
        "aliases": ["видеонаблюдение", "охранные системы", "СКУД", "пожарная сигнализация", "безопасность"],
        "business_models": ["project_sales", "services", "b2b_distribution"],
        "signals": ["complex_choice", "compatibility", "slow_quote", "lead_qualification"],
        "products": ["selection_consultant", "compatibility_agent", "quote_generator", "lead_qualifier"],
    },
]


def handbook() -> dict:
    return {
        "industries": INDUSTRIES,
        "business_models": BUSINESS_MODELS,
        "opportunity_patterns": OPPORTUNITY_PATTERNS,
        "ai_products": AI_PRODUCTS,
        "principle": "Каталог расширяемый: неизвестная отрасль не отбрасывается, а классифицируется агентом и помечается как кандидат на пополнение справочника.",
    }


def resolve_industries(requested: list[str]) -> list[dict]:
    if not requested:
        return INDUSTRIES
    normalized = {x.strip().lower() for x in requested if x.strip()}
    selected = []
    for item in INDUSTRIES:
        names = {item["id"].lower(), item["name"].lower(), *(x.lower() for x in item["aliases"])}
        if any(any(token in name or name in token for name in names) for token in normalized):
            selected.append(item)
    return selected or [
        {
            "id": "custom",
            "name": value,
            "aliases": [value],
            "business_models": list(BUSINESS_MODELS),
            "signals": list(OPPORTUNITY_PATTERNS),
            "products": list(AI_PRODUCTS),
        }
        for value in requested
    ]
