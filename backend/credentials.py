"""Write-only HTTP-facing API key storage backed by macOS Keychain."""

import ctypes
import getpass
import hashlib
import platform
import store


DEFAULTS = [{"id": "pixabay", "name": "Pixabay"}, {"id": "pexels", "name": "Pexels"}, {"id": "unsplash", "name": "Unsplash"}, {"id": "openrouter", "name": "OpenRouter"}]
_keychain = None


class MacKeychain:
    def __init__(self):
        if platform.system() != "Darwin":
            raise RuntimeError("Зв’язка ключів macOS недоступна")
        self.security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        self.foundation = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.security.SecKeychainFindGenericPassword.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        self.security.SecKeychainFindGenericPassword.restype = ctypes.c_int32
        self.security.SecKeychainAddGenericPassword.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
        self.security.SecKeychainAddGenericPassword.restype = ctypes.c_int32
        self.security.SecKeychainItemFreeContent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.security.SecKeychainItemFreeContent.restype = ctypes.c_int32
        self.security.SecKeychainItemModifyAttributesAndData.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
        self.security.SecKeychainItemModifyAttributesAndData.restype = ctypes.c_int32
        self.foundation.CFRelease.argtypes = [ctypes.c_void_p]
        self.foundation.CFRelease.restype = None

    def find(self, service):
        service = service.encode("utf-8")
        account = getpass.getuser().encode("utf-8")
        item = ctypes.c_void_p()
        status = self.security.SecKeychainFindGenericPassword(None, len(service), service, len(account), account, None, None, ctypes.byref(item))
        return status, item

    def configured(self, service):
        status, item = self.find(service)
        if item:
            self.foundation.CFRelease(item)
        return True if status == 0 else False if status == -25300 else None

    def read(self, service):
        service_bytes = service.encode("utf-8")
        account = getpass.getuser().encode("utf-8")
        length, data = ctypes.c_uint32(), ctypes.c_void_p()
        status = self.security.SecKeychainFindGenericPassword(None, len(service_bytes), service_bytes, len(account), account, ctypes.byref(length), ctypes.byref(data), None)
        if status:
            raise RuntimeError("Не вдалося отримати ключ OpenRouter зі зв’язки ключів macOS.")
        try:
            return ctypes.string_at(data, length.value).decode("utf-8")
        finally:
            if data:
                self.security.SecKeychainItemFreeContent(None, data)

    def save(self, service, secret):
        status, item = self.find(service)
        raw = secret.encode("utf-8")
        buffer = ctypes.create_string_buffer(raw)
        try:
            if status == 0:
                result = self.security.SecKeychainItemModifyAttributesAndData(item, None, len(raw), buffer)
            elif status == -25300:
                service_bytes = service.encode("utf-8")
                account = getpass.getuser().encode("utf-8")
                result = self.security.SecKeychainAddGenericPassword(None, len(service_bytes), service_bytes, len(account), account, len(raw), buffer, None)
            else:
                result = status
            if result:
                raise RuntimeError("Не вдалося зберегти ключ. Перевірте доступ до зв’язки ключів macOS.")
        finally:
            ctypes.memset(buffer, 0, len(buffer))
            if item:
                self.foundation.CFRelease(item)


def vault():
    global _keychain
    if _keychain is None:
        _keychain = MacKeychain()
    return _keychain


def service_name(provider_id):
    return "pixabay-youtube-api" if provider_id == "pixabay" else "multibot-video-studio-" + provider_id


def metadata_path():
    return store.DATA_ROOT / "service-providers.json"


def providers():
    custom = store.read_json(metadata_path(), [])
    result = []
    for provider in DEFAULTS + custom:
        try:
            configured = vault().configured(service_name(provider["id"]))
        except RuntimeError:
            configured = None
        result.append({"id": provider["id"], "name": provider["name"], "configured": configured})
    return result


def save_provider(provider_id, name, key):
    if not isinstance(key, str) or not 1 <= len(key.strip().encode("utf-8")) <= 8192 or any(ord(char) < 32 for char in key):
        raise store.StudioError("Введіть API-ключ без переносів рядка")
    custom = store.read_json(metadata_path(), [])
    if provider_id == "custom":
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60 or any(ord(char) < 32 for char in name):
            raise store.StudioError("Укажіть назву сервісу до 60 символів")
        name = name.strip()
        provider_id = "custom-" + hashlib.sha256(name.casefold().encode("utf-8")).hexdigest()[:16]
    elif provider_id not in {item["id"] for item in DEFAULTS + custom}:
        raise store.StudioError("Оберіть сервіс")
    try:
        vault().save(service_name(provider_id), key.strip())
    except RuntimeError as error:
        raise store.StudioError(str(error), 503) from None
    if provider_id.startswith("custom-"):
        with store.LOCK:
            custom = store.read_json(metadata_path(), [])
            if not any(item["id"] == provider_id for item in custom):
                custom.append({"id": provider_id, "name": name})
                store.atomic_json(metadata_path(), custom)
    return {"id": provider_id, "configured": True}
