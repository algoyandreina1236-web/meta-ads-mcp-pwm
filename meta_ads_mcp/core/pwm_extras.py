# -*- coding: utf-8 -*-
"""
Extras del fork meta-ads-mcp-pwm (Varimarket). Herramientas añadidas sobre el
paquete open source:
  - create_carousel_ad_creative : anuncios tipo CARRUSEL (2-10 tarjetas)
  - duplicate_campaign          : duplicar campañas (escalamiento horizontal)
  - create_page_post            : publicar posts ORGÁNICOS en la página
  - get_page_posts              : listar posts de la página con métricas
"""
import json
from typing import Optional, Dict, Any, List, Union

from .api import meta_api_tool, make_api_request, ensure_act_prefix
from .server import mcp_server


async def _get_page_access_token(page_id: Union[str, int], user_access_token: str) -> Optional[str]:
    """Obtiene el Page Access Token desde el user/system-user token.
    Requiere que ese usuario sea admin de la página. Devuelve None si no se pudo."""
    resp = await make_api_request(f"{page_id}", user_access_token, {"fields": "access_token"}, "GET")
    if isinstance(resp, dict):
        return resp.get("access_token")
    return None


@mcp_server.tool()
@meta_api_tool
async def create_carousel_ad_creative(
    account_id: str,
    page_id: Union[str, int],
    child_attachments: List[Dict[str, Any]],
    message: Optional[str] = None,
    link: Optional[str] = None,
    name: Optional[str] = None,
    call_to_action_type: Optional[str] = None,
    multi_share_end_card: bool = True,
    multi_share_optimized: bool = True,
    access_token: Optional[str] = None,
) -> str:
    """
    Crea un ad creative tipo CARRUSEL (2-10 tarjetas deslizables).

    Args:
        account_id: Cuenta publicitaria (act_XXXXXXXXX).
        page_id: Página de Facebook que publica el anuncio.
        child_attachments: Lista de 2 a 10 tarjetas. Cada tarjeta es un dict:
            {
              "link": "https://... (destino, requerido; si falta se usa 'link' global)",
              "image_hash": "hash de upload_ad_image",   # o "picture": "url publica"
              "name": "titular corto (opcional)",
              "description": "descripcion corta (opcional)",
              "call_to_action": {"type": "SHOP_NOW", "value": {"link": "..."}}  # opcional
            }
        message: Texto principal mostrado arriba del carrusel.
        link: URL por defecto para las tarjetas que no traigan su propio 'link'.
        name: Nombre interno del creativo.
        call_to_action_type: CTA global (SHOP_NOW, LEARN_MORE, WHATSAPP_MESSAGE, etc.)
            aplicado a las tarjetas que no traigan su propio call_to_action.
        multi_share_end_card: Mostrar tarjeta final con la foto de la Página (default True).
        multi_share_optimized: Dejar que Meta optimice el orden de las tarjetas (default True).

    Returns:
        JSON con el creative_id creado (o el error de Meta). Úsalo luego en create_ad.
    """
    account_id = ensure_act_prefix(account_id)

    default_link = link or (child_attachments[0].get("link") if child_attachments else None) or ""
    for card in child_attachments:
        if not card.get("link"):
            card["link"] = default_link
        if call_to_action_type and "call_to_action" not in card:
            if call_to_action_type == "WHATSAPP_MESSAGE":
                card["call_to_action"] = {"type": "WHATSAPP_MESSAGE"}
            else:
                card["call_to_action"] = {
                    "type": call_to_action_type,
                    "value": {"link": card.get("link", default_link)},
                }

    link_data: Dict[str, Any] = {
        "link": default_link,
        "child_attachments": child_attachments,
        "multi_share_end_card": multi_share_end_card,
        "multi_share_optimized": multi_share_optimized,
    }
    if message:
        link_data["message"] = message

    creative: Dict[str, Any] = {
        "object_story_spec": {"page_id": str(page_id), "link_data": link_data},
    }
    if name:
        creative["name"] = name

    endpoint = f"{account_id}/adcreatives"
    return await make_api_request(endpoint, access_token, creative, "POST")


@mcp_server.tool()
@meta_api_tool
async def duplicate_campaign(
    campaign_id: str,
    deep_copy: bool = True,
    status_option: str = "PAUSED",
    rename_suffix: Optional[str] = " - Copia",
    access_token: Optional[str] = None,
) -> str:
    """
    Duplica una campaña existente usando el endpoint /copies de Meta. Ideal para
    escalamiento horizontal (clonar una campaña que ya funciona).

    Args:
        campaign_id: ID de la campaña a duplicar.
        deep_copy: True (default) copia también sus conjuntos de anuncios y anuncios.
        status_option: Estado de la copia. 'PAUSED' (default, recomendado — la copia
            queda en pausa), 'INHERITED_FROM_SOURCE' o 'ACTIVE_PAUSED'.
        rename_suffix: Sufijo para el nombre de la copia (ej. ' - Copia').

    Returns:
        JSON con el id de la nueva campaña (copied_campaign_id) o el error de Meta.
    """
    params: Dict[str, Any] = {
        "deep_copy": deep_copy,
        "status_option": status_option,
    }
    if rename_suffix:
        params["rename_options"] = {"rename_suffix": rename_suffix}
    endpoint = f"{campaign_id}/copies"
    return await make_api_request(endpoint, access_token, params, "POST")


@mcp_server.tool()
@meta_api_tool
async def create_page_post(
    page_id: Union[str, int],
    message: Optional[str] = None,
    link: Optional[str] = None,
    image_url: Optional[str] = None,
    published: bool = True,
    access_token: Optional[str] = None,
) -> str:
    """
    Crea una publicación ORGÁNICA en la Página de Facebook (NO es un anuncio pago).

    Modos:
        - Solo texto: pasa 'message'.
        - Texto + enlace: 'message' + 'link'.
        - Foto: 'image_url' (URL pública de la imagen) + 'message' como pie de foto.

    Args:
        published: True publica de inmediato; False lo crea oculto (dark post) para
            luego promocionarlo como anuncio.
        access_token: token de usuario/system-user (se obtiene el Page Token solo).

    Requiere que el usuario/system-user sea administrador de la página.

    Returns:
        JSON con el id del post creado (o error).
    """
    page_token = await _get_page_access_token(page_id, access_token)
    if not page_token:
        return {
            "error": {
                "message": "No se pudo obtener el Page Access Token.",
                "action_required": "Verifica que el usuario del sistema tenga rol de administrador de la página en Business Manager.",
            }
        }

    if image_url:
        params: Dict[str, Any] = {"url": image_url, "published": published}
        if message:
            params["caption"] = message
        endpoint = f"{page_id}/photos"
    else:
        params = {"published": published}
        if message:
            params["message"] = message
        if link:
            params["link"] = link
        endpoint = f"{page_id}/feed"

    return await make_api_request(endpoint, page_token, params, "POST")


@mcp_server.tool()
@meta_api_tool
async def get_page_posts(
    page_id: Union[str, int],
    limit: int = 25,
    access_token: Optional[str] = None,
) -> str:
    """
    Lista las publicaciones ORGÁNICAS de la Página con sus métricas de interacción
    (reacciones, comentarios, compartidos) e insights (impresiones, alcance, clics).

    Args:
        page_id: ID de la Página de Facebook.
        limit: Máximo de publicaciones a devolver (default 25).

    Returns:
        JSON con la lista de posts: id, message, created_time, permalink_url, y los
        conteos de reacciones/comentarios/compartidos + insights por post.
    """
    page_token = await _get_page_access_token(page_id, access_token) or access_token
    params = {
        "limit": limit,
        "fields": (
            "id,message,created_time,permalink_url,shares,"
            "reactions.summary(total_count).limit(0),"
            "comments.summary(total_count).limit(0),"
            "insights.metric(post_impressions,post_impressions_unique,post_clicks)"
        ),
    }
    endpoint = f"{page_id}/posts"
    return await make_api_request(endpoint, page_token, params, "GET")
