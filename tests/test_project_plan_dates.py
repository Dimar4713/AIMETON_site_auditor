from scripts.project_plan_dates import planned_window, priority_days


def item(*, title='Task', kind='Issue', created='2026-08-01T08:00:00Z', closed=None, labels=()):
    return {
        '__typename': kind,
        'title': title,
        'createdAt': created,
        'closedAt': closed,
        'mergedAt': closed if kind == 'PullRequest' else None,
        'labels': {'nodes': [{'name': label} for label in labels]},
    }


def test_priority_windows_are_deterministic():
    assert priority_days('[P0] urgent', [], 'Issue') == 1
    assert priority_days('[P1] important', [], 'Issue') == 3
    assert priority_days('[P2] normal', [], 'Issue') == 7
    assert priority_days('[P3] later', [], 'Issue') == 14
    assert priority_days('PR', [], 'PullRequest') == 1
    assert priority_days('Issue', [], 'Issue') == 3


def test_open_p0_gets_one_day_window():
    assert planned_window(item(title='Task [P0]')) == ('2026-08-01', '2026-08-02')


def test_closed_item_uses_actual_close_as_safe_historical_finish():
    assert planned_window(item(closed='2026-08-04T11:00:00Z')) == ('2026-08-01', '2026-08-04')


def test_priority_label_is_supported():
    assert planned_window(item(labels=('priority:P2',))) == ('2026-08-01', '2026-08-08')
