"""设备注册与管理。

注册接口返回**一次性明文令牌**，客户端必须立刻写入 Keychain。
服务端只保存 `SHA256(token + salt)`，任何人拿到数据库也无法还原。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import identity
from app.database import get_db
from app.ratelimit import rate_limit
from app.schemas import (
    DeviceOut,
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    DeviceRenameRequest,
    DeviceScopesRequest,
)
from app.security import Caller, verify_token

logger = logging.getLogger("lumi.devices")
router = APIRouter(
    prefix="/api/v1/devices",
    tags=["devices"],
    dependencies=[Depends(verify_token), rate_limit("default")],
)


@router.post("", response_model=DeviceRegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: DeviceRegisterRequest, db: Session = Depends(get_db)):
    """注册一台新设备（iPhone / Windows 桌宠 / 脚本）。"""
    device, token = identity.register_device(
        db,
        name=payload.name,
        platform=payload.platform,
        app_version=payload.app_version,
        scopes=",".join(payload.scopes) if payload.scopes else None,
        user_id=payload.user_id,
    )
    db.commit()
    return DeviceRegisterResponse(
        device_id=device.id,
        user_id=device.user_id,
        name=device.name,
        platform=device.platform,
        token=token,
        token_hint=device.token_hint,
        scopes=device.scope_list,
        created_at=device.created_at.isoformat(),
    )


@router.get("", response_model=list[DeviceOut])
def list_all(db: Session = Depends(get_db)):
    return [d.to_dict() for d in identity.list_devices(db)]


@router.patch("/{device_id}", response_model=DeviceOut)
def rename(device_id: str, payload: DeviceRenameRequest, db: Session = Depends(get_db)):
    device = identity.rename_device(db, device_id, payload.name)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "设备不存在。", "hint": None},
        )
    db.commit()
    return device.to_dict()


@router.put("/{device_id}/scopes", response_model=DeviceOut)
def set_scopes(device_id: str, payload: DeviceScopesRequest, db: Session = Depends(get_db)):
    device = identity.set_scopes(db, device_id, payload.scopes)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "设备不存在。", "hint": None},
        )
    db.commit()
    return device.to_dict()


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke(device_id: str, db: Session = Depends(get_db)):
    """吊销设备：令牌立即失效，已保存的会话数据保留。"""
    if not identity.revoke_device(db, device_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "设备不存在或已吊销。", "hint": None},
        )
    db.commit()


@router.get("/me", tags=["devices"])
def whoami(caller: Caller = Depends(verify_token)) -> dict:
    """客户端自检：确认当前令牌身份与权限。"""
    return {
        "kind": caller.kind,
        "user_id": caller.user_id,
        "device_id": caller.device_id,
        "scopes": sorted(caller.scopes),
    }
