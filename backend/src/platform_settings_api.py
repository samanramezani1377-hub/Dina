from __future__ import annotations
import base64, hashlib
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet
from .auth import token_user_id
from .config import get_settings
from .platform_admin_api import _conn, require_platform_admin
from .errors import ApiError, ErrorCode

router=APIRouter(prefix="/api/v1/platform/settings",tags=["platform-settings"])

ALLOWED_KEYS={
 "zarinpal_merchant_id","zarinpal_callback_url","zarinpal_webhook_secret",
 "taxpayer_system_username","taxpayer_system_password","taxpayer_system_client_id",
 "taxpayer_system_client_secret","taxpayer_system_fiscal_id","taxpayer_system_api_url",
 "backup_database_url","backup_storage_url","backup_access_key","backup_secret_key",
 "monitoring_dsn","monitoring_alert_webhook","android_keystore_b64","android_key_alias",
 "android_key_password","android_store_password","windows_signing_certificate_b64",
 "windows_signing_password","e2e_base_url","e2e_token"
}
SECRET_KEYS=ALLOWED_KEYS-{ "zarinpal_callback_url","taxpayer_system_api_url","backup_storage_url","monitoring_dsn","e2e_base_url","android_key_alias"}

class SettingIn(BaseModel):
 value:str=Field(max_length=10000)

def _fernet():
    raw=get_settings().require_secret_key().encode()
    key=base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)

@router.get("")
def get_settings_page(_:int=Depends(require_platform_admin)):
    with _conn() as c:
        rows=c.execute("SELECT setting_key,is_secret,updated_at FROM platform_settings ORDER BY setting_key").fetchall()
    return {"items":[{"key":r["setting_key"],"is_secret":r["is_secret"],"configured":True,"updated_at":r["updated_at"]} for r in rows]}

@router.get("/{key}")
def get_setting(key:str,_:int=Depends(require_platform_admin)):
    if key not in ALLOWED_KEYS: raise ApiError(ErrorCode.NOT_FOUND,"setting not found")
    with _conn() as c: row=c.execute("SELECT setting_value,is_secret,updated_at FROM platform_settings WHERE setting_key=%s",(key,)).fetchone()
    if not row: return {"key":key,"configured":False,"value":""}
    if row["is_secret"]:
        return {"key":key,"configured":True,"is_secret":True,"value":"","masked":"••••••••","updated_at":row["updated_at"]}
    value=_fernet().decrypt(row["setting_value"].encode()).decode()
    return {"key":key,"configured":True,"is_secret":False,"value":value,"updated_at":row["updated_at"]}

@router.put("/{key}")
def put_setting(key:str,p:SettingIn,user_id:int=Depends(require_platform_admin)):
    if key not in ALLOWED_KEYS: raise ApiError(ErrorCode.NOT_FOUND,"setting not found")
    encrypted=_fernet().encrypt(p.value.encode()).decode()
    with _conn() as c:
        return c.execute("""INSERT INTO platform_settings(setting_key,setting_value,is_secret,updated_by)
          VALUES(%s,%s,%s,%s)
          ON CONFLICT(setting_key) DO UPDATE SET setting_value=EXCLUDED.setting_value,is_secret=EXCLUDED.is_secret,updated_by=EXCLUDED.updated_by,updated_at=NOW()
          RETURNING setting_key,is_secret,updated_at""",(key,encrypted,key in SECRET_KEYS,user_id)).fetchone()
