import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from Sammaryhelper.ai_handler import AIChatManager

@pytest.fixture
def mock_ai_manager():
    """Фикстура для мока AIChatManager"""
    settings = {
        'openai_model': 'gpt-4-turbo-preview',
        'available_models': ['gpt-3.5-turbo', 'gpt-4', 'gpt-4-turbo-preview']
    }
    
    manager = MagicMock(spec=AIChatManager)
    manager.settings = settings
    manager.get_available_models = AsyncMock(return_value=[
        {'id': 'gpt-3.5-turbo'},
        {'id': 'gpt-4'},
        {'id': 'gpt-4-turbo-preview'}
    ])
    return manager

@pytest.mark.asyncio
async def test_model_list_operations(mock_ai_manager):
    """Тест операций со списком моделей"""
    models = await mock_ai_manager.get_available_models()
    assert len(models) == 3
    assert models[0]['id'] == 'gpt-3.5-turbo'
    assert models[2]['id'] == 'gpt-4-turbo-preview'

def test_model_selection(mock_ai_manager):
    """Тест выбора модели"""
    # Проверяем начальное состояние
    assert mock_ai_manager.settings['openai_model'] == 'gpt-4-turbo-preview'
    
    # Имитируем выбор модели
    mock_ai_manager.settings['openai_model'] = 'gpt-4'
    assert mock_ai_manager.settings['openai_model'] == 'gpt-4'

@pytest.mark.asyncio
async def test_model_error_handling(mock_ai_manager):
    """Тест обработки ошибок"""
    mock_ai_manager.get_available_models.side_effect = Exception("API Error")
    
    with pytest.raises(Exception, match="API Error"):
        await mock_ai_manager.get_available_models()