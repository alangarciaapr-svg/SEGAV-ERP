"""Confirmaciones visuales globales para acciones de SEGAV ERP.

Objetivo: que cada acción de modificación deje una respuesta visible y
uniforme para el usuario, incluso cuando Streamlit ejecuta `st.rerun()`.
"""
from __future__ import annotations

from html import escape
import re
from typing import Any, Callable

import streamlit as st

_FLASH_KEY = "_segav_action_feedback_queue"
_PATCHED_FLAG = "_segav_action_feedback_installed"
_TOAST_COUNTER_KEY = "_segav_action_feedback_toast_counter"
_MAX_FLASH_MESSAGES = 4

_DESTRUCTIVE_RE = re.compile(
    r"\b(eliminad[oa]s?|borrad[oa]s?|quitad[oa]s?|rechazad[oa]s?|desactivad[oa]s?|revocad[oa]s?)\b",
    re.IGNORECASE,
)

_ACTION_MESSAGES: dict[str, tuple[str, str]] = {
    # Trabajadores
    "trabajador": ("success", "Trabajador creado correctamente."),
    "trabajador_edit": ("success", "Trabajador actualizado correctamente."),
    "trabajador_delete": ("delete", "Trabajador eliminado."),
    "import_excel": ("success", "Importación de trabajadores completada correctamente."),
    "mass_docs_import": ("success", "Importación masiva de documentos completada correctamente."),
    # Asignaciones
    "asignacion": ("success", "Trabajadores asignados correctamente."),
    "asignacion_remove": ("delete", "Trabajadores quitados de la faena."),
    "import_asignar_faena": ("success", "Importación y asignación a faena completada correctamente."),
    # Documentos
    "doc_empresa": ("success", "Documento empresa guardado correctamente."),
    "doc_empresa_delete": ("delete", "Documento empresa eliminado."),
    "doc_empresa_faena_mensual": ("success", "Documento empresa por faena guardado correctamente."),
    "doc_empresa_faena_delete": ("delete", "Documento empresa por faena eliminado."),
    "doc_trabajador": ("success", "Documento de trabajador guardado correctamente."),
    "doc_trabajador_delete": ("delete", "Documento de trabajador eliminado."),
    # Exportaciones y respaldos
    "export_zip": ("success", "ZIP generado y guardado correctamente."),
    "export_zip_mes": ("success", "ZIP mensual generado y guardado correctamente."),
    "backup_restore": ("success", "Backup restaurado correctamente."),
    # Usuarios
    "users_create": ("success", "Usuario creado correctamente o enviado a aprobación."),
    "users_update": ("success", "Usuario actualizado correctamente."),
    "users_delete": ("delete", "Usuario eliminado correctamente."),
    "user_approve": ("success", "Usuario aprobado y activado correctamente."),
    "user_reject": ("delete", "Usuario rechazado correctamente."),
    "company_access_limits": ("success", "Límites de acceso guardados correctamente."),
    "company_user_access": ("success", "Permisos por empresa actualizados correctamente."),
    # Mandantes, contratos y faenas
    "mandante": ("success", "Mandante creado correctamente."),
    "mandante_edit": ("success", "Mandante actualizado correctamente."),
    "mandante_delete": ("delete", "Mandante eliminado."),
    "contrato_faena": ("success", "Contrato de faena creado correctamente."),
    "contrato_edit": ("success", "Contrato actualizado correctamente."),
    "contrato_archivo": ("success", "Archivo de contrato actualizado correctamente."),
    "contrato_delete": ("delete", "Contrato eliminado."),
    "faena": ("success", "Faena creada correctamente."),
    "faena_edit": ("success", "Faena actualizada correctamente."),
    "faena_delete": ("delete", "Faena eliminada."),
    "anexo_faena": ("success", "Anexo de faena guardado correctamente."),
    # Configuración y SGSST
    "segav_config": ("success", "Configuración ERP guardada correctamente."),
    "sgsst_save": ("success", "Registro SGSST guardado correctamente."),
}


def _plain_text(value: Any) -> str:
    try:
        if value is None:
            return ""
        return str(value)
    except Exception:
        return ""


def _looks_destructive(message: Any) -> bool:
    text = _plain_text(message)
    return bool(_DESTRUCTIVE_RE.search(text))


def _call_with_default_icon(func: Callable[..., Any], body: Any, default_icon: str, *args: Any, **kwargs: Any) -> Any:
    # No pisa iconos explícitos enviados por el código existente.
    if not args and "icon" not in kwargs:
        kwargs["icon"] = default_icon
    return func(body, *args, **kwargs)


def _compact_message(body: Any) -> str:
    text = _plain_text(body).strip()
    if len(text) <= 180:
        return text
    return text[:177].rstrip() + "..."


def _floating_toast(body: Any, *, icon: str, kind: str) -> Any:
    message = _compact_message(body)
    safe_kind = str(kind or "success").lower()
    if safe_kind not in {"success", "delete", "error", "danger", "warning", "info"}:
        safe_kind = "success"
    try:
        idx = int(st.session_state.get(_TOAST_COUNTER_KEY, 0) or 0) % _MAX_FLASH_MESSAGES
        st.session_state[_TOAST_COUNTER_KEY] = (idx + 1) % _MAX_FLASH_MESSAGES
    except Exception:
        idx = 0
    return st.markdown(
        f'''
        <div class="segav-floating-toast segav-toast-{safe_kind}" style="--segav-toast-index:{idx};">
          <span class="segav-toast-icon">{escape(str(icon or ""))}</span>
          <span class="segav-toast-message">{escape(message)}</span>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def install_action_feedback() -> None:
    """Instala wrappers visuales sobre st.success/error/warning una sola vez.

    Esto mantiene compatibilidad con el código existente, pero estandariza iconos
    y fuerza que acciones destructivas comunicadas como `success` aparezcan en rojo.
    """
    if getattr(st, _PATCHED_FLAG, False):
        return

    original_success = st.success
    original_error = st.error
    original_warning = st.warning
    original_info = st.info

    def _flash(body: Any, icon: str, kind: str, fallback: Callable[..., Any]) -> Any:
        # Muestra el aviso como toast flotante; la posición final la define el CSS global.
        # Si st.toast no estuviera disponible, cae al alert en línea de siempre.
        message = _compact_message(body)
        try:
            return _floating_toast(message, icon=icon, kind=kind)
        except Exception:
            try:
                return fallback(message, icon=icon)
            except Exception:
                return fallback(message)

    def success(body: Any = None, *args: Any, **kwargs: Any) -> Any:
        icon = kwargs.get("icon")
        if _looks_destructive(body):
            return _flash(body, icon or "×", "delete", original_error)
        return _flash(body, icon or "✓", "success", original_success)

    def error(body: Any = None, *args: Any, **kwargs: Any) -> Any:
        icon = kwargs.get("icon")
        return _flash(body, icon or "!", "error", original_error)

    def warning(body: Any = None, *args: Any, **kwargs: Any) -> Any:
        return _call_with_default_icon(original_warning, body, "⚠️", *args, **kwargs)

    def info(body: Any = None, *args: Any, **kwargs: Any) -> Any:
        return _call_with_default_icon(original_info, body, "ℹ️", *args, **kwargs)

    st.success = success  # type: ignore[assignment]
    st.error = error  # type: ignore[assignment]
    st.warning = warning  # type: ignore[assignment]
    st.info = info  # type: ignore[assignment]
    setattr(st, _PATCHED_FLAG, True)


def notify_success(message: str) -> None:
    install_action_feedback()
    st.success(message)


def notify_error(message: str) -> None:
    install_action_feedback()
    st.error(message)


def notify_warning(message: str) -> None:
    install_action_feedback()
    try:
        _floating_toast(message, icon="!", kind="warning")
    except Exception:
        st.warning(message)


def notify_delete(message: str) -> None:
    install_action_feedback()
    # Acción destructiva: rojo aunque técnicamente haya sido exitosa.
    st.error(message, icon="×")


def queue_action_feedback(kind: str, message: str) -> None:
    """Guarda una confirmación para mostrarla tras `st.rerun()`."""
    if not message:
        return
    queue = list(st.session_state.get(_FLASH_KEY, []))
    item = {"kind": kind or "success", "message": _compact_message(message)}
    if not queue or queue[-1] != item:
        queue.append(item)
    # Evita acumular mensajes antiguos si el usuario ejecuta muchas acciones rápidas.
    st.session_state[_FLASH_KEY] = queue[-_MAX_FLASH_MESSAGES:]


def queue_action_feedback_from_tag(tag: str | None) -> None:
    """Convierte etiquetas internas de backup/auditoría en mensajes de usuario."""
    key = str(tag or "").strip()
    if not key:
        return
    kind, message = _ACTION_MESSAGES.get(key, _fallback_from_tag(key))
    queue_action_feedback(kind, message)


def render_action_feedback() -> None:
    """Muestra y limpia confirmaciones pendientes."""
    install_action_feedback()
    queue = list(st.session_state.pop(_FLASH_KEY, []) or [])
    for item in queue:
        kind = str(item.get("kind") or "success").lower()
        message = str(item.get("message") or "").strip()
        if not message:
            continue
        if kind in {"delete", "deleted", "destructive"}:
            notify_delete(message)
        elif kind in {"error", "danger"}:
            notify_error(message)
        elif kind in {"warning", "warn"}:
            notify_warning(message)
        else:
            notify_success(message)


def _fallback_from_tag(tag: str) -> tuple[str, str]:
    low = tag.lower()
    entity = tag.replace("_", " ").strip().capitalize() or "Acción"
    if any(word in low for word in ("delete", "remove", "eliminar", "quit")):
        return "delete", f"{entity} eliminado correctamente."
    if any(word in low for word in ("edit", "update", "actualiz")):
        return "success", f"{entity} actualizado correctamente."
    if any(word in low for word in ("create", "insert", "nuevo", "add")):
        return "success", f"{entity} creado correctamente."
    return "success", f"Acción completada correctamente: {entity}."
