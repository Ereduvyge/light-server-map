"""Password-protected SQLAdmin views using the application's async sessions."""

import secrets
from pathlib import Path

from fastapi import FastAPI
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqladmin.fields import JSONField
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request
from wtforms import Form, SelectField
from wtforms.validators import IPAddress, NumberRange

from config import Settings
from db.models import Node, Software, SoftwareTypes


class AdminAuth(AuthenticationBackend):
    def __init__(self, password: str):
        super().__init__(
            secret_key=secrets.token_urlsafe(32),
            session_cookie="light_server_map_admin",
            path="/admin",
            max_age=8 * 60 * 60,
            same_site="lax",
        )
        self._password = password.encode("utf-8")

    async def login(self, request: Request) -> bool:
        form = await request.form()
        password = form.get("password", "")
        request.session.clear()
        if not isinstance(password, str):
            return False
        if not secrets.compare_digest(password.encode("utf-8"), self._password):
            return False
        request.session["user_id"] = "admin"
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return request.session.get("user_id") == "admin"


class NodeAdmin(ModelView, model=Node):
    name_plural = "Nodes"
    icon = "fa-solid fa-server"
    column_list = [
        Node.id, Node.name, Node.ip, Node.ping_check_enabled,
        Node.ping_check_every, Node.is_ping_ok, Node.last_checked_at,
    ]
    column_searchable_list = [Node.name, Node.ip]
    column_sortable_list = [Node.id, Node.name, Node.ip, Node.last_checked_at]
    column_default_sort = (Node.id, False)
    column_details_list = column_list
    form_columns = [
        Node.name, Node.ip, Node.ping_check_enabled,
        Node.ping_check_every, Node.notificatons_enabled,
    ]
    form_args = {
        "ip": {"validators": [IPAddress(ipv4=True, ipv6=True)]},
        "ping_check_every": {"validators": [NumberRange(min=1)]},
    }
    column_labels = {
        Node.ping_check_every: "Ping interval (seconds)",
        Node.notificatons_enabled: "Notifications enabled",
    }

class SoftwareAdmin(ModelView, model=Software):
    name_plural = "Software"
    icon = "fa-solid fa-cubes"
    column_list = [
        Software.id, Software.name, Software.node, Software.type,
        Software.health_check_enabled, Software.is_healthy, Software.last_checked_at,
    ]
    column_searchable_list = [Software.name, Software.domain]
    column_sortable_list = [Software.id, Software.name, Software.last_checked_at]
    column_default_sort = (Software.id, False)
    column_details_list = column_list + [
        Software.domain, Software.port, Software.health_check_path,
        Software.health_check_every, Software.meta,
    ]
    form_columns = [
        Software.name, Software.node, Software.type, Software.domain, Software.port,
        Software.health_check_path, Software.health_check_enabled,
        Software.health_check_every, Software.notificatons_enabled,
    ]
    form_overrides = {"type": SelectField}
    form_args = {
        "type": {"choices": [
            (SoftwareTypes.APP.value, "Application"),
            (SoftwareTypes.DB.value, "Database"),
        ]},
        "port": {"validators": [NumberRange(min=1, max=65535)]},
        "health_check_every": {"validators": [NumberRange(min=1)]},
    }
    column_formatters = {Software.node: lambda model, _attribute: model.node.name}
    column_formatters_detail = column_formatters
    column_labels = {
        Software.health_check_every: "Health check interval (seconds)",
        Software.notificatons_enabled: "Notifications enabled",
    }

    async def get_object_for_edit(self, request: Request):
        software = await super().get_object_for_edit(request)
        if software is not None:
            software.metadata_json = software.meta
        return software

    async def on_model_change(
        self, data: dict, model: Software, is_created: bool, request: Request
    ) -> None:
        data["meta"] = data.pop("metadata_json", None)


def mount_admin(
    app: FastAPI, sessions: async_sessionmaker[AsyncSession], settings: Settings
) -> Admin:
    admin = Admin(
        app,
        session_maker=sessions,
        base_url="/admin",
        title="Light Server Map Admin",
        templates_dir=str(Path(__file__).resolve().parents[1] / "templates"),
        authentication_backend=AdminAuth(settings.ADMIN_PASSWORD.get_secret_value()),
    )
    admin.add_view(NodeAdmin)
    admin.add_view(SoftwareAdmin)
    return admin
