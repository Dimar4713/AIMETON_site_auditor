# AIMETON Embodied Runtime · сервер как тело развивающегося системного актора

## Статус

**Статус:** `EXPERIMENTAL_CONCEPT`

**Ветка:** `experiment/dynamic-site-rendering`

**Назначение:** зафиксировать архитектурную идею устойчивого вычислительного тела AIMETON, которое развивается по мере решения задач, приобретает новые способности, сохраняет историю изменений и формирует непрерывность системного актора.

## 1. Базовая идея

Сервер рассматривается не только как место размещения приложения, а как постоянное вычислительное тело AIMETON.

```text
задача
→ напряжение и дефицит способности
→ поиск средства
→ проба
→ ошибка или успех
→ закрепление работающего решения
→ появление нового устойчивого навыка
```

Аналогии:

- сервер — тело;
- ОС — базовая физиология;
- Runtime — нервная система;
- Capability Registry — память приобретённых навыков;
- Capability Scout — исследовательская функция;
- Policy Engine — иммунитет и система запретов;
- Git — биография и наследуемая история развития;
- задачи — среда, которая заставляет актора расти.

## 2. Что считается ростом

Установка пакета сама по себе не является приобретённой способностью.

Рост произошёл только тогда, когда система:

1. поняла, зачем способность нужна;
2. обнаружила Capability Gap;
3. выбрала или создала реализацию;
4. установила её в подходящую среду;
5. научилась вызывать её через контракт;
6. проверила результат;
7. поняла ограничения и риски;
8. встроила её в общий Runtime;
9. сохранила код, тесты и доказательства;
10. может повторно использовать способность после перезапуска.

## 3. Жизненный цикл способности

```text
DISCOVERED
→ CANDIDATE
→ SANDBOXED
→ TESTED
→ ACCEPTED
→ ACTIVE
→ DEGRADED
→ RETIRED
```

Человеко-подобное прочтение:

```text
обнаружена
→ примерена
→ временно подключена
→ испытана
→ освоена
→ встроена
→ поддерживается
→ утрачена или заменена
```

## 4. Effective Capability

Наличие программной реализации ещё не означает наличие рабочей способности.

```text
Effective Capability
=
Implementation
× Environment Permissions
× Runtime Resources
× External Access
× Trust Policy
```

Если любой множитель фактически равен нулю, способность отсутствует.

Отсюда требуется не только Capability Passport, но и Execution Environment Passport.

## 5. Execution Environment Passport

Минимальный паспорт среды должен фиксировать:

```yaml
environment:
  operating_system: Ubuntu
  cpu: unknown
  memory_mb: unknown
  storage_gb: unknown

  network:
    outbound_https: unknown
    dns_resolution: unknown
    inbound_ports: []

  processes:
    subprocess_spawn: unknown
    browser_processes: unknown
    docker_allowed: unknown

  system_packages:
    install_allowed: unknown
    sudo_available: unknown

  persistence:
    durable_storage: unknown
    backup_available: unknown

  security:
    firewall_state: unknown
    ssh_policy: unknown
    secrets_storage: unknown
```

## 6. Контур телесного развития

```text
Task
↓
Required Capability
↓
Capability Gap
↓
Environment Inspection
↓
Capability Scout
↓
Candidate Implementation
↓
Provisioning
↓
Sandbox Tests
↓
Security and Contract Tests
↓
Capability Acceptance
↓
Runtime Integration
↓
Observed Result
↓
Capability Evaluation
↓
Registry and Body Memory Update
```

## 7. AIMETON Embodied Runtime

Предлагаемый слой:

**AIMETON Embodied Runtime — телесный контур системного актора**

Состав:

```text
Compute Body
Storage Body
Network Body
Execution Organs
Observation Organs
Capability Organs
Immune and Safety Layer
Body Memory
Body Development History
```

Жизненный цикл тела:

```text
Birth
→ Baseline Formation
→ Environment Exploration
→ Capability Acquisition
→ Skill Consolidation
→ Structural Adaptation
→ Maintenance
→ Recovery
→ Evolution
```

## 8. Непрерывность актора

Чтобы сервер был одним растущим телом, а не новой программой после каждого запуска, должны устойчиво сохраняться:

- идентичность;
- история задач;
- приобретённые способности;
- результаты тестов;
- причины выбора инструментов;
- неудачные эксперименты;
- модель собственного тела;
- текущее состояние;
- ограничения и мандаты.

```text
одно и то же тело
+ непрерывная память
+ история изменений
= непрерывность системного актора
```

## 9. Отличие от обычного DevOps

Обычная схема:

```text
человек заранее знает архитектуру
→ человек пишет конфигурацию
→ сервер исполняет
```

Схема AIMETON:

```text
система получает задачу
→ сама обнаруживает, чего не хватает
→ строит гипотезы расширения
→ испытывает варианты
→ формирует собственную рабочую архитектуру
```

Это переход от развёртывания приложения к выращиванию системного актора.

## 10. Мандат и безопасность

Развивающееся тело не должно иметь неограниченную свободу.

Автономно допустимы:

- установка пакетов из доверенных источников;
- создание контейнеров;
- работа внутри выделенного каталога AIMETON;
- запуск тестов;
- создание экспериментальных Git-веток;
- откат собственных изменений.

Требуют human approval:

- изменение firewall и SSH;
- открытие внешних портов;
- подключение платных сервисов;
- расходы сверх лимита;
- изменение `main`;
- удаление значимых данных;
- публикация наружу;
- работа с чужими системами.

## 11. Первый натурный эксперимент

Исходная среда:

```text
пустой VPS
+ базовая Ubuntu
+ SSH
+ отдельный пользователь с sudo
+ исходящий интернет
```

Цель:

> Самостоятельно обследовать сервер, создать Environment Passport, развернуть AIMETON Site Auditor, приобрести способность dynamic_site_rendering, провести минимум три реальных анализа сайтов и зарегистрировать новую способность с доказательствами.

Этапы:

```text
1. Инвентаризация сервера
2. Environment Passport
3. Установка минимального базового контура
4. Развёртывание Capability Lab
5. Развёртывание Site Auditor
6. Capability Gap Analysis
7. Установка и тест Playwright
8. Contract/security/integration tests
9. Три реальных сайта
10. Capability Passport
11. Registry update
12. Итоговый отчёт и Git-история
```

## 12. Главный вывод

Саморазвитие невозможно без собственного устойчивого пространства, которое система имеет право изменять и за состояние которого несёт ответственность.

Песочница даёт временную мастерскую.

Постоянный сервер даёт AIMETON тело, память, биографию и возможность взрослеть.
