"""
app/ipam/collectors/field_schema.py
--------------------------------------
Small builder helpers for describing a collector type's config fields to
the Collectors UI, shared by the dhcp/dns/device registries. Each
collector type's "fields" list used to just be a flat list of field
*names* (`["base_url", "username", ...]`) — the frontend had nothing to
render but a raw JSON textarea. These builders instead produce a schema
dict per field (key/label/type/required/placeholder/help/options/
sub_fields) so the UI can render a real form.

This is metadata only — it doesn't change what a collector's `config`
dict looks like at runtime (still a plain dict, same keys), only how the
UI helps build one.

`show_if` lets a field only render when another field in the same form
currently equals a given value — used for collectors that offer more than
one auth mode (e.g. UniFi: API key vs username/password) so the form only
shows the fields relevant to the selected mode instead of both sets at
once.
"""
from __future__ import annotations


def _show_if(show_if: tuple[str, str] | None) -> dict | None:
    if show_if is None:
        return None
    key, equals = show_if
    return {"key": key, "equals": equals}


def text(key: str, label: str, *, required: bool = False, placeholder: str = "", help: str = "",
         show_if: tuple[str, str] | None = None) -> dict:
    return {"key": key, "label": label, "type": "text", "required": required, "placeholder": placeholder,
            "help": help, "show_if": _show_if(show_if)}


def password(key: str, label: str, *, required: bool = False, placeholder: str = "", help: str = "",
             show_if: tuple[str, str] | None = None) -> dict:
    return {"key": key, "label": label, "type": "password", "required": required, "placeholder": placeholder,
            "help": help, "show_if": _show_if(show_if)}


def number(key: str, label: str, *, required: bool = False, default: int | float | None = None, help: str = "",
           show_if: tuple[str, str] | None = None) -> dict:
    return {"key": key, "label": label, "type": "number", "required": required, "default": default,
            "help": help, "show_if": _show_if(show_if)}


def toggle(key: str, label: str, *, default: bool = False, help: str = "",
           show_if: tuple[str, str] | None = None) -> dict:
    return {"key": key, "label": label, "type": "toggle", "default": default, "help": help,
            "show_if": _show_if(show_if)}


def select(key: str, label: str, options: list[tuple[str, str]], *, required: bool = False,
           default: str | None = None, help: str = "", show_if: tuple[str, str] | None = None) -> dict:
    return {
        "key": key, "label": label, "type": "select", "required": required, "help": help,
        "default": default, "options": [{"value": v, "label": lbl} for v, lbl in options],
        "show_if": _show_if(show_if),
    }


def multiselect(key: str, label: str, options: list[tuple[str, str]], *, default: list[str] | None = None,
                 help: str = "", show_if: tuple[str, str] | None = None) -> dict:
    return {
        "key": key, "label": label, "type": "multiselect", "help": help,
        "default": default or [], "options": [{"value": v, "label": lbl} for v, lbl in options],
        "show_if": _show_if(show_if),
    }


def string_list(key: str, label: str, *, help: str = "", item_placeholder: str = "",
                 show_if: tuple[str, str] | None = None) -> dict:
    return {"key": key, "label": label, "type": "string_list", "help": help,
            "item_placeholder": item_placeholder, "show_if": _show_if(show_if)}


def host_list(key: str, label: str, sub_fields: list[dict], *, help: str = "",
              show_if: tuple[str, str] | None = None) -> dict:
    return {"key": key, "label": label, "type": "host_list", "help": help, "sub_fields": sub_fields,
            "show_if": _show_if(show_if)}


def site_select(key: str, label: str, *, help: str = "", show_if: tuple[str, str] | None = None) -> dict:
    """A dropdown populated from the app's managed Sites list (/api/sites)
    instead of a free-typed string — same UX as SiteSelect.tsx elsewhere in
    the app. The frontend fetches the sites list itself; this schema entry
    just marks the field as that kind of picker."""
    return {"key": key, "label": label, "type": "site_select", "help": help, "show_if": _show_if(show_if)}


def credential_select(key: str, label: str, *, required: bool = False, help: str = "",
                       show_if: tuple[str, str] | None = None) -> dict:
    """A dropdown populated from the app's managed SNMP Credentials list
    (/api/snmp-credentials, managed under Settings) instead of asking a
    collector's own setup form to re-collect a full community string/v3
    auth+priv passphrase set every time — same pattern as pktsnmp's
    Settings -> SNMP -> Credentials tab. The frontend fetches the
    credentials list itself; this schema entry just marks the field as
    that kind of picker. Resolved to real SNMP auth fields at poll time by
    app/ipam/poll_engine.py, not by the collector itself."""
    return {"key": key, "label": label, "type": "credential_select", "required": required,
            "help": help, "show_if": _show_if(show_if)}


def pktsnmp_select(key: str, label: str, *, required: bool = False, help: str = "",
                    show_if: tuple[str, str] | None = None) -> dict:
    """A dropdown populated from the app's named pktsnmp connections
    (/api/integrations, managed under Settings -> Security -> Suite
    Integration) instead of asking a collector's own setup form to
    re-collect a base_url + suite_token every time. The frontend fetches
    the integrations list itself and shows a link to the Suite Integration
    setup screen when none exist yet. Resolved to real base_url/
    suite_token fields at poll time by app/ipam/poll_engine.py, not by the
    collector itself — same pattern as credential_select."""
    return {"key": key, "label": label, "type": "pktsnmp_select", "required": required,
            "help": help, "show_if": _show_if(show_if)}
