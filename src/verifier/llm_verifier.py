"""LLM verifier for lead qualification."""

import asyncio
from datetime import datetime
from typing import Optional
import aiosqlite

from database import DATABASE_FILE


class LLMVerifier:
    """LLM-based lead verifier with few-shot learning."""
    
    def __init__(
        self,
        provider: str,
        api_key: str,
        model: Optional[str] = None,
        max_concurrent: int = 10,
        timeout: int = 30,
        max_retries: int = 3,
        max_spam_examples: int = 20,
        spam_cache_update_interval: int = 60
    ):
        """
        Initialize LLM verifier.
        
        Args:
            provider: "claude", "openai", or "openrouter"
            api_key: API key for the provider
            model: Model name (optional, uses defaults if not specified)
            max_concurrent: Maximum concurrent API requests
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            max_spam_examples: Maximum spam examples in prompt
            spam_cache_update_interval: Spam cache update interval in seconds
        """
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_spam_examples = max_spam_examples
        self.spam_cache_update_interval = spam_cache_update_interval
        
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._spam_cache: list[str] = []
        self._cache_update_task: Optional[asyncio.Task] = None
        
        # Initialize API client
        if provider == "claude":
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(api_key=api_key)
                self._default_model = "claude-3-haiku-20240307"
            except ImportError:
                raise ImportError("anthropic package not installed. Run: pip install anthropic")
        elif provider == "openai":
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=api_key)
                self._default_model = "gpt-4o-mini"
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")
        elif provider == "openrouter":
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=api_key,
                    base_url="https://openrouter.ai/api/v1"
                )
                self._default_model = "anthropic/claude-3.5-haiku"
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")
        else:
            raise ValueError(f"Unknown provider: {provider}")

    
    async def start_spam_cache_update(self) -> None:
        """Start background task to update spam cache."""
        if self._cache_update_task is None or self._cache_update_task.done():
            self._cache_update_task = asyncio.create_task(self._update_spam_cache_loop())
    
    async def stop_spam_cache_update(self) -> None:
        """Stop spam cache update task."""
        if self._cache_update_task and not self._cache_update_task.done():
            self._cache_update_task.cancel()
            try:
                await self._cache_update_task
            except asyncio.CancelledError:
                pass
    
    async def _update_spam_cache_loop(self) -> None:
        """Background task to update spam cache."""
        while True:
            try:
                await self._update_spam_cache()
                await asyncio.sleep(self.spam_cache_update_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error updating spam cache: {e}")
                await asyncio.sleep(self.spam_cache_update_interval)
    
    async def _update_spam_cache(self) -> None:
        """Update spam cache from database."""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            cursor = await db.execute(
                "SELECT message_text FROM spam_database ORDER BY created_at DESC LIMIT ?",
                (self.max_spam_examples,)
            )
            rows = await cursor.fetchall()
            self._spam_cache = [row[0] for row in rows]

    
    async def verify_lead(self, message_text: str) -> bool:
        """
        Verify if message is a qualified lead using LLM.
        
        Args:
            message_text: Message text to verify
            
        Returns:
            True if qualified lead, False otherwise
        """
        async with self._semaphore:
            for attempt in range(self.max_retries):
                try:
                    prompt = await self._build_prompt(message_text)
                    response = await asyncio.wait_for(
                        self._call_llm_api(prompt),
                        timeout=self.timeout
                    )
                    return self._parse_response(response)
                except asyncio.TimeoutError:
                    if attempt == self.max_retries - 1:
                        print(f"LLM timeout after {self.max_retries} attempts")
                        return False
                    await asyncio.sleep(1)
                except Exception as e:
                    if attempt == self.max_retries - 1:
                        print(f"LLM API error after {self.max_retries} attempts: {e}")
                        return False
                    # Exponential backoff
                    await asyncio.sleep(2 ** attempt)
        
        return False

    
    async def _build_prompt(self, message_text: str) -> str:
        """Build few-shot prompt with spam examples."""
        system_prompt = """Ты классификатор лидов для IT-услуг.

ЗАДАЧА: Определи, является ли сообщение реальным запросом на услуги разработки/дизайна.

КРИТЕРИИ РЕАЛЬНОГО ЗАПРОСА:
- Явное указание на потребность в услуге
- Описание задачи или проекта
- Вопросы о стоимости/сроках
- Поиск исполнителя

НЕ ЯВЛЯЕТСЯ ЗАПРОСОМ:
- Реклама услуг
- Предложения работы
- Общие обсуждения
- Спам и флуд
"""
        
        # Add negative examples if available
        if self._spam_cache:
            system_prompt += "\n\nПРИМЕРЫ СПАМА (НЕ лиды):\n"
            for i, spam_example in enumerate(self._spam_cache, 1):
                system_prompt += f'{i}. "{spam_example}"\n'
        
        system_prompt += f'\n\nСООБЩЕНИЕ ДЛЯ АНАЛИЗА:\n"{message_text}"\n\n'
        system_prompt += 'ОТВЕТ (только "ДА" или "НЕТ"):'
        
        return system_prompt

    
    async def _call_llm_api(self, prompt: str) -> str:
        """Call LLM API."""
        model = self.model or self._default_model
        
        if self.provider == "claude":
            response = await self._client.messages.create(
                model=model,
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        elif self.provider in ["openai", "openrouter"]:
            response = await self._client.chat.completions.create(
                model=model,
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _parse_response(self, response: str) -> bool:
        """Parse LLM response to boolean."""
        response_clean = response.strip().upper()
        # Check for positive responses
        if "ДА" in response_clean or "YES" in response_clean:
            return True
        return False
