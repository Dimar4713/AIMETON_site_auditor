from pathlib import Path
import pytest
from app.scraper import extract_visible_text
from app.heuristics import heuristic_analysis

@pytest.mark.parametrize('name,expected', [('dns','Розничная и электронная торговля'),('timeweb','Облачная инфраструктура и хостинг'),('cdek','Логистика и доставка')])
def test_three_sites(name, expected):
    html=Path(f'tests/fixtures/{name}.html').read_text(encoding='utf-8')
    title,text=extract_visible_text(html)
    result=heuristic_analysis(f'https://{name}.example',title,text)
    assert expected in result.business_summary
    assert 5 <= len(result.agents) <= 10
    assert all(a.name and a.purpose and a.benefit for a in result.agents)
