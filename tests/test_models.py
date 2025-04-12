import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from Sammaryhelper.ai_handler import AIChatManager

@pytest.fixture
def ai_manager():
    settings = {
        'openai_api_key': 'test_key',
        'openai_model': 'gpt-3.5-turbo',
        'system_prompt': 'Test prompt'
    }
    return AIChatManager(settings)

@pytest.mark.asyncio
async def test_get_available_models_success(ai_manager):
    """Тест успешного получения списка моделей"""
    mock_models = [
        MagicMock(id='gpt-4', created=12345, owned_by='openai'),
        MagicMock(id='gpt-3.5-turbo', created=12344, owned_by='openai')
    ]
    
    with patch('openai.AsyncOpenAI') as mock_openai:
        mock_client = AsyncMock()
        mock_client.models.list.return_value = MagicMock(data=mock_models)
        mock_openai.return_value = mock_client
        
        models = await ai_manager.get_available_models()
        
        assert len(models) == 2
        assert models[0]['id'] == 'gpt-4'
        assert models[1]['id'] == 'gpt-3.5-turbo'
        assert isinstance(models[0]['capabilities'], dict)

@pytest.mark.asyncio
async def test_get_available_models_error(ai_manager):
    """Тест обработки ошибок при получении списка моделей"""
    with patch('openai.AsyncOpenAI') as mock_openai:
        mock_client = AsyncMock()
        mock_client.models.list.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client
        
        models = await ai_manager.get_available_models()
        
        assert models == []

@pytest.mark.asyncio
async def test_select_and_save_model(ai_manager, monkeypatch):
    """Тест выбора и сохранения модели"""
    # Подготовка тестовых данных
    mock_models = [
        {'id': 'gpt-4', 'created': 12345, 'owned_by': 'openai', 
         'capabilities': {'chat': True, 'completion': False, 'embedding': False}},
        {'id': 'gpt-3.5-turbo', 'created': 12344, 'owned_by': 'openai',
         'capabilities': {'chat': True, 'completion': False, 'embedding': False}}
    ]
    
    # Мок для get_available_models
    async def mock_get_models():
        return mock_models
        
    ai_manager.get_available_models = mock_get_models
    
    # Эмуляция ввода пользователя (выбор модели 1)
    monkeypatch.setattr('builtins.input', lambda _: "1")
    
    # Выполнение выбора модели
    selected_model = await ai_manager.select_model()
    
    # Проверки
    assert selected_model == 'gpt-4'
    assert ai_manager.settings['openai_model'] == 'gpt-4'

@pytest.mark.asyncio
async def test_select_model_cancel(ai_manager, monkeypatch):
    """Тест отмены выбора модели"""
    # Мок для get_available_models
    async def mock_get_models():
        return [{'id': 'gpt-4', 'created': 12345, 'owned_by': 'openai'}]
        
    ai_manager.get_available_models = mock_get_models
    
    # Эмуляция ввода пользователя (отмена)
    monkeypatch.setattr('builtins.input', lambda _: "0")
    
    selected_model = await ai_manager.select_model()
    
    assert selected_model == ""
    assert ai_manager.settings['openai_model'] == 'gpt-3.5-turbo'  # Значение по умолчанию