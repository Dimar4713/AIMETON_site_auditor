import inspect

from app.search_observer_llm import evaluate_search_wave_shadow_with_model


def test_shadow_prompt_pins_continue_vs_refine_calibration() -> None:
    source = inspect.getsource(evaluate_search_wave_shadow_with_model)

    assert "Отличай continue от refine" in source
    assert "конкретный диагностический сигнал" in source
    assert "предпочитай continue" in source
    assert "Не вводи собственные числовые пороги" in source
    assert "routing_changed всегда false" in source
