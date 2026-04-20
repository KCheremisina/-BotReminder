import os
import logging
from typing import Optional, Tuple
from telegram.request import HTTPXRequest
import httpx
from telegram.ext import Application

logger = logging.getLogger(__name__)

class ProxyManager:
    
    def __init__(self, proxy_url: Optional[str] = None, 
                 proxy_username: Optional[str] = None,
                 proxy_password: Optional[str] = None,
                 proxy_type: str = "socks5",
                 mtproto_secret: Optional[str] = None):
        self.proxy_url = proxy_url
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        self.proxy_type = proxy_type.lower()
        self.mtproto_secret = mtproto_secret
        self._client = None
        
    def is_configured(self) -> bool:
        return bool(self.proxy_url)
    
    def get_proxy_info(self) -> dict:
        if not self.proxy_url:
            return {"enabled": False}
        
        masked_url = self._mask_url(self.proxy_url)
        
        return {
            "enabled": True,
            "type": self.proxy_type,
            "url": masked_url,
            "has_auth": bool(self.proxy_username and self.proxy_password),
            "mtproto": bool(self.mtproto_secret)
        }
    
    def _build_proxy_url(self) -> Optional[str]:
        if not self.proxy_url:
            return None
        
        if '://' in self.proxy_url:
            base_url = self.proxy_url
        else:
            if self.proxy_type == 'mtproto':
                base_url = f"socks5://{self.proxy_url}"
            else:
                base_url = f"{self.proxy_type}://{self.proxy_url}"
        
        if self.proxy_username and self.proxy_password:
            if self.proxy_type in ['socks4', 'socks5', 'http', 'https']:
                parts = base_url.split('://')
                if len(parts) == 2:
                    auth_part = f"{self.proxy_username}:{self.proxy_password}@"
                    return f"{parts[0]}://{auth_part}{parts[1]}"
        
        return base_url
    
    def create_client(self) -> Optional[httpx.AsyncClient]:
        if not self.proxy_url:
            return None
        
        try:
            proxy_full_url = self._build_proxy_url()
            if not proxy_full_url:
                return None
            
            logger.info(f"🔧 Создаю клиент с прокси: {self._mask_url(proxy_full_url)}")
            
            if self.proxy_type == 'mtproto':
                logger.error("❌ MTProto прокси не поддерживается в httpx")
                logger.info("💡 Используйте socks5 прокси вместо MTProto")
                return None
            
            self._client = httpx.AsyncClient(
                proxies=proxy_full_url,
                verify=False,
                timeout=30.0,
                follow_redirects=True
            )
            
            logger.info(f"✅ Прокси-клиент создан ({self.proxy_type}): {self._mask_url(self.proxy_url)}")
            return self._client
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания прокси-клиента: {e}")
            return None
    
    def create_request(self) -> Optional[HTTPXRequest]:
        if not self.proxy_url:
            return None
        
        try:
            if not self._client:
                self.create_client()
            
            if self._client:
                return HTTPXRequest(client=self._client)
            else:
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка создания request с прокси: {e}")
            return None
    
    def create_application(self, token: str) -> Application:
        if not self.proxy_url:
            return Application.builder().token(token).build()
        
        try:
            request = self.create_request()
            if request:
                application = Application.builder() \
                    .token(token) \
                    .request(request) \
                    .build()
                logger.info("✅ Приложение создано с прокси")
                return application
            else:
                logger.warning("⚠️ Не удалось создать request с прокси, работаем без прокси")
                return Application.builder().token(token).build()
                
        except Exception as e:
            logger.error(f"❌ Ошибка настройки прокси: {e}")
            logger.warning("⚠️ Запуск без прокси")
            return Application.builder().token(token).build()
    
    async def test_connection(self) -> Tuple[bool, str]:
        if not self.proxy_url:
            return False, "Прокси не настроен"
        
        try:
            if not self._client:
                self.create_client()
            
            if not self._client:
                return False, "Не удалось создать клиент"
            
            response = await self._client.get(
                "https://api.telegram.org/bot", 
                timeout=10.0
            )
            
            if response.status_code in [200, 403]:
                return True, f"✅ Подключение успешно (статус: {response.status_code})"
            else:
                return False, f"❌ Ошибка подключения (статус: {response.status_code})"
                
        except Exception as e:
            return False, f"❌ Ошибка: {str(e)}"
    
    async def test_mtproto_connection(self, bot_token: str) -> Tuple[bool, str]:
        if not self.proxy_url or self.proxy_type != 'mtproto':
            return False, "MTProto прокси не настроен"
        
        return False, "MTProto прокси не поддерживается. Используйте стандартный socks5 прокси"
    
    async def close(self):
        if self._client:
            await self._client.aclose()
            logger.info("🔒 Прокси-соединение закрыто")
    
    def _mask_url(self, url: str) -> str:
        if not url:
            return url
        
        import re
        pattern = r'(:[^:@]+@)'
        match = re.search(pattern, url)
        if match:
            return url.replace(match.group(1), ':***@')
        return url


_proxy_manager = None
_proxy_manager_lock = None

def _get_lock():
    global _proxy_manager_lock
    if _proxy_manager_lock is None:
        import threading
        _proxy_manager_lock = threading.Lock()
    return _proxy_manager_lock

def get_proxy_manager(proxy_url: Optional[str] = None,
                     proxy_username: Optional[str] = None,
                     proxy_password: Optional[str] = None,
                     proxy_type: str = "socks5",
                     mtproto_secret: Optional[str] = None) -> ProxyManager:
    global _proxy_manager
    
    with _get_lock():
        if _proxy_manager is None:
            _proxy_manager = ProxyManager(
                proxy_url, proxy_username, proxy_password, 
                proxy_type, mtproto_secret
            )
        return _proxy_manager

def reset_proxy_manager():
    global _proxy_manager
    
    with _get_lock():
        if _proxy_manager:
            try:
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    asyncio.create_task(_proxy_manager.close())
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(_proxy_manager.close())
                    loop.close()
            except:
                pass
        _proxy_manager = None