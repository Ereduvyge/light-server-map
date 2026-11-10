"""Full-page and HTMX fragment routes for the node map."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db.models import Node

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


def check_status(enabled: bool, healthy: bool | None, checked_at) -> dict[str, str]:
    if not enabled:
        return {"color": "disabled", "label": "Disabled"}
    if checked_at is None or healthy is None:
        return {"color": "unknown", "label": "Not checked"}
    return {
        "color": "healthy" if healthy else "unhealthy",
        "label": "Healthy" if healthy else "Unreachable",
    }


def node_health(node: Node) -> str:
    """Summarize enabled checks: failure, pending, healthy, or all disabled."""
    statuses = {
        check_status(node.ping_check_enabled, node.is_ping_ok, node.last_checked_at)["color"]
    }
    statuses.update(
        check_status(item.health_check_enabled, item.is_healthy, item.last_checked_at)["color"]
        for item in node.softwares
    )
    for status in ("unhealthy", "unknown", "healthy"):
        if status in statuses:
            return status
    return "disabled"


templates.env.globals["check_status"] = check_status
templates.env.globals["node_health"] = node_health


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


async def get_node(request: Request, node_id: int, *, software: bool = False) -> Node:
    node = await request.app.state.db.get_entity(
        Node, node_id, load_relationships=[Node.softwares] if software else None
    )
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.get("/", response_class=HTMLResponse)
async def map_page(request: Request):
    nodes = await request.app.state.db.get_entities(
        Node, load_relationships=[Node.softwares], sort="id"
    )
    return templates.TemplateResponse(
        request=request, name="pages/map.html", context={"nodes": nodes}
    )


@router.get("/components/nodes", response_class=HTMLResponse)
async def node_list(request: Request):
    nodes = await request.app.state.db.get_entities(
        Node, load_relationships=[Node.softwares], sort="id"
    )
    return templates.TemplateResponse(
        request=request, name="components/nodes.html", context={"nodes": nodes}
    )


@router.get("/components/nodes/{node_id}", response_class=HTMLResponse)
async def node_card(request: Request, node_id: int):
    node = await get_node(request, node_id, software=True)
    return templates.TemplateResponse(
        request=request, name="components/node.html", context={"node": node}
    )


@router.get("/components/nodes/{node_id}/status", response_class=HTMLResponse)
async def node_status(request: Request, node_id: int):
    node = await get_node(request, node_id, software=True)
    return templates.TemplateResponse(
        request=request, name="components/node_details.html", context={"node": node}
    )


@router.get("/components/nodes/{node_id}/software", response_class=HTMLResponse)
async def software_panel(request: Request, node_id: int):
    node = await get_node(request, node_id, software=True)
    return templates.TemplateResponse(
        request=request, name="components/software_panel.html", context={"node": node}
    )
